from __future__ import unicode_literals

import os
import decimal
import datetime
import inspect
import six
import mimetypes

from collections import OrderedDict

from django.conf import settings
from django.db.models import Model
from django.db.models.query import QuerySet
from django.db.models.fields.files import FileField

try:
    from django.db.models.fields.related import ForeignRelatedObjectsDescriptor, SingleRelatedObjectDescriptor
except ImportError:
    from django.db.models.fields.related import (ReverseManyToOneDescriptor as ForeignRelatedObjectsDescriptor,
                                                 ReverseOneToOneDescriptor as SingleRelatedObjectDescriptor)

from django.utils import formats, timezone
from django.utils.encoding import force_text
from django.utils.translation import ugettext
from django.utils.html import conditional_escape

from chamber.utils.datastructures import Enum
from chamber.utils import get_class_method

from .exception import UnsupportedMediaTypeException
from .utils import rfs
from .utils.compatibility import get_reverse_field_name, get_last_parent_pk_field_name
from .utils.helpers import QuerysetIteratorHelper, UniversalBytesIO
from .converter import get_converter


default_serializers = []


def register(serialized_types):
    """
    Adds throttling validator to a class.
    """
    def _register(klass):
        if klass not in (serializer for _, serializer in default_serializers):
            default_serializers.insert(0, (serialized_types, klass))
        return klass
    return _register


def get_resource_or_none(request, thing):
    from .resource import typemapper

    resource_class = typemapper.get(thing.model if isinstance(thing, QuerySet) else type(thing))
    return resource_class(request) if resource_class else None


def get_serializer(thing, request=None):
    if request:
        resource = get_resource_or_none(request, thing)
        if resource:
            return resource.serializer(resource, request=request)

    for serialized_types, serializer in default_serializers:
        if isinstance(thing, serialized_types):
            return serializer(request=request)
    return DefaultSerializer(request=request)


class RawVerboseValue(object):
    """
    Return RAW, VERBOSE or BOTH values according to serialization type
    """

    def __init__(self, raw_value, verbose_value):
        self.raw_value = raw_value
        self.verbose_value = verbose_value

    def get_value(self, serialization_format):
        if serialization_format == Serializer.SERIALIZATION_TYPES.RAW:
            return self.raw_value
        elif serialization_format == Serializer.SERIALIZATION_TYPES.VERBOSE:
            return self.verbose_value
        elif self.raw_value == self.verbose_value:
            return self.raw_value
        else:
            return {'_raw': self.raw_value, '_verbose': self.verbose_value}


class LazySerializedData(object):

    def __init__(self, serializer, data, serialization_format, **kwargs):
        self.serializer = serializer
        self.data = data
        self.serialization_format = serialization_format
        self.kwargs = kwargs

    def serialize(self):
        return self.serializer.serialize(self.data, self.serialization_format, **self.kwargs)


class Serializer(object):
    """
    REST serializer and deserializer, firstly is data serialized to standard python data types and after that is
    used convertor for final serialization
    """

    SERIALIZATION_TYPES = Enum('VERBOSE', 'RAW', 'BOTH')

    def __init__(self, request=None):
        self.request = request

    def _data_to_python(self, data, serialization_format, lazy=False, **kwargs):
        return get_serializer(data, request=self.request).serialize(data, serialization_format, **kwargs)

    def _lazy_data_to_python(self, data, serialization_format, lazy=False, **kwargs):
        if lazy:
            return LazySerializedData(
                get_serializer(data, request=self.request), data, serialization_format, lazy=lazy, **kwargs
            )
        else:
            return self._data_to_python(data, serialization_format, lazy=lazy, **kwargs)

    def serialize(self, data, serialization_format, **kwargs):
        raise NotImplementedError

    def deserialize(self, data):
        raise NotImplementedError


class ResourceSerializerMixin(object):

    def __init__(self, resource, request=None):
        self.resource = resource
        super(ResourceSerializerMixin, self).__init__(request=request)

    def deserialize(self, data):
        return data


class ResourceSerializer(ResourceSerializerMixin, Serializer):
    """
    Default resource serializer perform serialization to th client format
    """

    def serialize(self, data, serialization_format, **kwargs):
        return self._data_to_python(data, serialization_format, **kwargs)


@register(six.string_types)
class StringSerializer(Serializer):

    def serialize(self, data, serialization_format, **kwargs):
        return conditional_escape(force_text(data, strings_only=True))


class DefaultSerializer(Serializer):

    def serialize(self, data, serialization_format, **kwargs):
        return force_text(data, strings_only=True)


@register(datetime.datetime)
class DateTimeSerializer(Serializer):

    def serialize(self, data, serialization_format, **kwargs):
        return timezone.localtime(data)


@register(dict)
class DictSerializer(Serializer):

    def serialize(self, data, serialization_format, requested_fieldset=None,
                   extended_fieldset=None, exclude_fields=None, **kwargs):
        return dict([(k, self._data_to_python(v, serialization_format, **kwargs))
                     for k, v in data.items()])


@register((list, tuple, set))
class CollectionsSerializer(Serializer):

    def serialize(self, data, serialization_format, requested_fieldset=None,
                   extended_fieldset=None, exclude_fields=None, **kwargs):
        return (self._data_to_python(v, serialization_format, **kwargs) for v in data)


@register(decimal.Decimal)
class DecimalSerializer(Serializer):

    def serialize(self, data, serialization_format, **kwargs):
        return data


@register(RawVerboseValue)
class RawVerboseSerializer(Serializer):

    def serialize(self, data, serialization_format, lazy=False, **kwargs):
        return self._data_to_python(data.get_value(serialization_format), serialization_format, lazy=False, **kwargs)


@register((Model, QuerySet, QuerysetIteratorHelper))
class ModelSerializer(Serializer):

    RESERVED_FIELDS = {'read', 'update', 'create', 'delete', 'model', 'allowed_methods', 'fields', 'exclude'}

    def _get_resource_method_fields(self, resource, fields):
        out = {}
        for field in fields.flat() - self.RESERVED_FIELDS:
            t = getattr(resource, str(field), None)
            if t and callable(t):
                out[field] = t
        return out

    def _get_model_fields(self, obj):
        out = {}
        for f in obj._meta.fields:
            if hasattr(f, 'serialize') and f.serialize:
                out[f.name] = f
        return out

    def _get_m2m_fields(self, obj):
        out = {}
        for mf in obj._meta.many_to_many:
            if mf.serialize:
                out[mf.name] = mf
        return out

    def _get_verbose_value(self, raw, field_or_method, obj, **kwargs):
        if hasattr(field_or_method, 'humanized') and field_or_method.humanized:
            return field_or_method.humanized(raw, obj, **kwargs)
        elif hasattr(field_or_method, 'choices') and field_or_method.choices:
            return getattr(obj, 'get_{}_display'.format(field_or_method.attname))()
        if isinstance(raw, bool):
            return raw and ugettext('Yes') or ugettext('No')
        elif isinstance(raw, datetime.datetime):
            return formats.localize(timezone.template_localtime(raw))
        elif isinstance(raw, (datetime.date, datetime.time)):
            return formats.localize(raw)
        else:
            return raw

    def _value_to_raw_verbose(self, val, field_or_method, obj, **kwargs):
        return RawVerboseValue(val, self._get_verbose_value(val, field_or_method, obj, **kwargs))

    def _method_to_python(self, method, obj, serialization_format, **kwargs):
        method_kwargs_names = inspect.getargspec(method)[0][1:]

        method_kwargs = {}

        fun_kwargs = {'request': kwargs.get('request'), 'obj': obj} if 'request' in kwargs else {'obj': obj}

        for arg_name in method_kwargs_names:
            if arg_name in fun_kwargs:
                method_kwargs[arg_name] = fun_kwargs[arg_name]

        if len(method_kwargs_names) == len(method_kwargs):
            return self._data_to_python(
                self._value_to_raw_verbose(method(**method_kwargs), method, obj,
                                           **{k: v for k, v in method_kwargs.items() if k != 'obj'}),
                serialization_format, allow_tags=getattr(method, 'allow_tags', False), **kwargs
            )

    def _model_field_to_python(self, field, obj, serialization_format, **kwargs):
        return (self._lazy_data_to_python if field.is_relation else self._data_to_python)(
            self._value_to_raw_verbose(self._get_model_field_raw_value(obj, field), field, obj)
            if not field.rel else getattr(obj, field.name),
            serialization_format, allow_tags=getattr(field, 'allow_tags', False), **kwargs
        )

    def _m2m_field_to_python(self, field, obj, serialization_format, **kwargs):
        return (self._data_to_python(m, serialization_format, allow_tags=getattr(field, 'allow_tags', False), **kwargs)
                for m in getattr(obj, field.name).all())

    def _get_reverse_excluded_fields(self, field, obj):
        model = obj.__class__
        exclude_fields = []
        if hasattr(model, field) and isinstance(getattr(model, field, None),
                                                (ForeignRelatedObjectsDescriptor, SingleRelatedObjectDescriptor)):
            exclude_fields.append(get_reverse_field_name(model, field))

        return exclude_fields

    def _reverse_qs_to_python(self, val, field, obj, serialization_format, **kwargs):
        kwargs['exclude_fields'] = self._get_reverse_excluded_fields(field, obj)
        return (self._data_to_python(m, serialization_format, **kwargs) for m in val.all())

    def _reverse_to_python(self, val, field, obj, serialization_format, **kwargs):
        kwargs['exclude_fields'] = self._get_reverse_excluded_fields(field, obj)
        return self._lazy_data_to_python(val, serialization_format, **kwargs)

    def _copy_kwargs(self, resource, kwargs):
        subkwargs = kwargs.copy()
        subkwargs['exclude_fields'] = None
        subkwargs['via'] = resource._get_via(kwargs.get('via')) if resource else kwargs.get('via')
        return subkwargs

    def _get_field_name(self, field, requested_field, subkwargs):
        if field.subfieldset:
            field_name, subkwargs['extended_fieldset'] = field.name, field.subfieldset
        else:
            field_name, subkwargs['extended_fieldset'] = field.name, None

        if requested_field and requested_field.subfieldset:
            subkwargs['requested_fieldset'] = requested_field.subfieldset
        elif field.subfieldset:
            subkwargs['requested_fieldset'] = field.subfieldset

        return field_name

    def _get_file_field_value(self, val):
        if val:
            filename = os.path.basename(val.name)
            return {
                'filename': filename,
                'content_type': (
                    mimetypes.types_map.get('.{}'.format(filename.split('.')[-1])) if '.' in filename else None
                ),
                'url': val.url,
            }
        else:
            return None

    def _get_model_field_raw_value(self, obj, field):
        val = getattr(obj, field.attname)
        return self._get_file_field_value(val) if isinstance(field, FileField) else val

    def _field_to_python(self, field_name, resource_method_fields, model_fields, m2m_fields,
                         obj, serialization_format, **kwargs):
        if field_name == '_obj_name':
            return force_text(obj)
        elif field_name in resource_method_fields:
            return self._method_to_python(resource_method_fields[field_name], obj, serialization_format,
                                          **kwargs)
        elif field_name in m2m_fields:
            return self._m2m_field_to_python(m2m_fields[field_name], obj, serialization_format, **kwargs)
        elif field_name in model_fields:
            return self._model_field_to_python(model_fields[field_name], obj, serialization_format, **kwargs)
        else:
            val = getattr(obj, field_name, None) if hasattr(obj, field_name) else None
            if hasattr(val, 'all'):
                return self._reverse_qs_to_python(val, field_name, obj, serialization_format, **kwargs)
            elif isinstance(val, Model):
                return self._reverse_to_python(val, field_name, obj, serialization_format, **kwargs)
            elif callable(val):
                return self._method_to_python(val, obj, serialization_format, **kwargs)
            else:
                method = get_class_method(obj, field_name)
                return self._data_to_python(self._value_to_raw_verbose(val, method, obj), serialization_format,
                                            allow_tags=method is not None and getattr(method, 'allow_tags', False),
                                            **kwargs)

    def _fields_to_python(self, obj, serialization_format, fieldset, requested_fieldset, **kwargs):
        model_resource = self._get_model_resource(obj)
        resource_method_fields = self._get_resource_method_fields(model_resource, fieldset)
        model_fields = self._get_model_fields(obj)
        m2m_fields = self._get_m2m_fields(obj)

        out = OrderedDict()

        for field in fieldset.fields:
            subkwargs = self._copy_kwargs(model_resource, kwargs)
            requested_field = None
            if requested_fieldset:
                requested_field = requested_fieldset.get(field.name)
            field_name = self._get_field_name(field, requested_field, subkwargs)
            out[field_name] = self._field_to_python(
                field_name, resource_method_fields, model_fields, m2m_fields, obj, serialization_format, **subkwargs
            )

        return out

    def _get_model_resource(self, obj):
        return None

    def _get_fieldset_from_resource(self, model_resource, obj, via, has_get_permission):
        if not has_get_permission:
            return model_resource.get_guest_fields(obj)
        else:
            return model_resource.get_default_general_fields(obj)

    def _get_allowed_fieldset_from_resource(self, model_resource, obj, via, has_get_permission):
        if not has_get_permission:
            return model_resource.get_guest_fields(obj)
        else:
            return model_resource.get_fields(obj)

    def _get_fieldset(self, obj, extended_fieldset, requested_fieldset, exclude_fields, via, direct_serialization,
                      serialized_objects):

        if self._get_obj_serialization_name(obj) in serialized_objects:
            return rfs((get_last_parent_pk_field_name(obj),))

        model_resource = self._get_model_resource(obj)

        if model_resource:
            has_get_permission = (model_resource.has_get_permission(obj, via) or
                                  model_resource.has_post_permission(obj, via) or
                                  model_resource.has_put_permission(obj, via))
            default_fieldset = self._get_fieldset_from_resource(model_resource, obj, via, has_get_permission)
            allowed_fieldset = self._get_allowed_fieldset_from_resource(model_resource, obj, via, has_get_permission)
        else:
            allowed_fieldset = (
                (requested_fieldset if requested_fieldset else rfs(
                    obj._rest_meta.extra_fields
                 ).join(rfs(obj._rest_meta.default_general_fields)).join(
                    rfs(obj._rest_meta.default_detailed_fields)
                 ).join(rfs(obj._rest_meta.direct_serialization_fields)))
                if direct_serialization else rfs(obj._rest_meta.guest_fields)
            )
            default_fieldset = (
                rfs(obj._rest_meta.direct_serialization_fields)
                if direct_serialization else rfs(obj._rest_meta.guest_fields)
            )

        if extended_fieldset:
            default_fieldset.join(extended_fieldset)
            allowed_fieldset.join(extended_fieldset)

        if requested_fieldset:
            # requested_fieldset must be cloned because RFS is not immutable and intersection change it
            fieldset = rfs(requested_fieldset).intersection(allowed_fieldset).extend_fields_fieldsets(default_fieldset)
        else:
            fieldset = default_fieldset.intersection(allowed_fieldset)

        if exclude_fields:
            fieldset.subtract(exclude_fields)
        return fieldset

    def _get_obj_serialization_name(self, obj):
        return '{}__{}'.format(obj._meta.db_table, obj.pk)

    def _obj_to_python(self, obj, serialization_format, requested_fieldset=None, extended_fieldset=None,
                       exclude_fields=None, allow_tags=False, direct_serialization=False,
                       serialized_objects=None, **kwargs):
        exclude_fields = [] if exclude_fields is None else exclude_fields
        serialized_objects = set() if serialized_objects is None else set(serialized_objects)
        fieldset = self._get_fieldset(obj, extended_fieldset, requested_fieldset, exclude_fields,
                                      kwargs.get('via'), direct_serialization, serialized_objects)
        serialized_objects.add(self._get_obj_serialization_name(obj))
        return self._fields_to_python(obj, serialization_format, fieldset, requested_fieldset,
                                      serialized_objects=serialized_objects,
                                      direct_serialization=direct_serialization, **kwargs)

    def serialize(self, data, serialization_format, **kwargs):
        if isinstance(data, QuerysetIteratorHelper):
            return (self._obj_to_python(obj, serialization_format, **kwargs) for obj in data.iterator())
        elif isinstance(data, QuerySet):
            return (self._obj_to_python(obj, serialization_format, **kwargs) for obj in data)
        elif isinstance(data, Model):
            return self._obj_to_python(data, serialization_format, **kwargs)
        else:
            raise NotImplementedError


class ModelResourceSerializer(ResourceSerializerMixin, ModelSerializer):

    def _get_model_resource(self, obj):
        return self.resource

    def serialize(self, data, serialization_format, **kwargs):
        if isinstance(data, (QuerysetIteratorHelper, QuerySet, Model)):
            return super(ModelResourceSerializer, self).serialize(data, serialization_format, **kwargs)
        else:
            return self._data_to_python(data, serialization_format, **kwargs)


def serialize(data, requested_fieldset=None, serialization_format=Serializer.SERIALIZATION_TYPES.RAW,
              converter_name=None, converter_options=None):
    converter_name = (
        converter_name if converter_name is not None else getattr(settings, 'PYSTON_DEFAULT_CONVERTER', 'json')
    )
    requested_fieldset = rfs(requested_fieldset) if requested_fieldset is not None else None
    converted_dict = get_serializer(data).serialize(
        data, serialization_format, requested_fieldset=requested_fieldset, direct_serialization=True
    )
    if converter_name == 'python':
        return converted_dict
    else:
        try:
            converter, _ = get_converter(converter_name)
        except ValueError:
            raise UnsupportedMediaTypeException
        converter_options = (
            converter_options if converter_options is not None
            else getattr(settings, 'DEFAULT_DIRECT_SERIALIZATION_CONVERTER_OPTIONS', {}).get(converter_name, {})
        )
        os = UniversalBytesIO()
        converter().encode_to_stream(os, converted_dict, converter_options)
        return os.get_string_value()
