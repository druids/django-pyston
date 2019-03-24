import os
import decimal
import datetime
import inspect
import mimetypes
import types

from collections import OrderedDict

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

from .conf import settings
from .exception import UnsupportedMediaTypeException, NotAllowedException
from .utils import rfs
from .utils.compatibility import get_reverse_field_name, get_last_parent_pk_field_name
from .utils.helpers import QuerysetIteratorHelper, UniversalBytesIO, serialized_data_to_python, str_to_class
from .converters import get_converter
from .forms import RESTDictError, RESTListError, RESTDictIndexError


default_serializers = []


class Serializable:

    def serialize(self, serialization_format, **kwargs):
        raise NotImplementedError


class SerializableObj(Serializable):

    resource_typemapper = {}

    def _get_value(self, field, serialization_format, request, **kwargs):
        val = getattr(self, field)
        return get_serializer(
            val, request=request, resource_typemapper=self.resource_typemapper
        ).serialize(val, serialization_format, **kwargs)

    def serialize(self, serialization_format, request=None, **kwargs):
        return {field_name: self._get_value(field_name, serialization_format, request, **kwargs)
                for field_name in self.get_fields()}

    def get_fields(self):
        return self.RESTMeta.fields


class SerializationException(Exception):
    pass


def register(serialized_types):
    """
    Adds throttling validator to a class.
    """
    def _register(klass):
        if klass not in (serializer for _, serializer in default_serializers):
            default_serializers.insert(0, (serialized_types, klass))
        return klass
    return _register


def get_resource_class_or_none(thing, resource_typemapper=None):
    from .resource import typemapper as global_resource_typemapper

    resource_typemapper = {} if resource_typemapper is None else resource_typemapper
    resource_class = resource_typemapper.get(thing) or global_resource_typemapper.get(thing)
    if isinstance(resource_class, str):
        resource_class = str_to_class(resource_class)
    return resource_class


def get_resource_or_none(request, thing, resource_typemapper=None):
    from .resource import typemapper as global_resource_typemapper

    resource_class = get_resource_class_or_none(thing, resource_typemapper)
    return resource_class(request) if resource_class else None


def get_serializer(thing, request=None, resource_typemapper=None):
    if request:
        thing_class = thing.model if isinstance(thing, QuerySet) else type(thing)
        resource = get_resource_or_none(request, thing_class, resource_typemapper)
        if resource:
            return resource.serializer(resource, request=request)

    for serialized_types, serializer in default_serializers:
        if isinstance(thing, serialized_types):
            return serializer(request=request)
    return DefaultSerializer(request=request)


class RawVerboseValue:
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


class LazySerializedData:

    def __init__(self, serializer, data, serialization_format, **kwargs):
        self.serializer = serializer
        self.data = data
        self.serialization_format = serialization_format
        self.kwargs = kwargs

    def serialize(self):
        return self.serializer.serialize(self.data, self.serialization_format, **self.kwargs)


class LazyMappedSerializedData:

    def __init__(self, data, data_mapping):
        self.data = data
        self.data_mapping = data_mapping

    def _map_key(self, lookup_key):
        return self.data_mapping.get(lookup_key, lookup_key)

    def serialize(self):
        if isinstance(self.data, RESTDictError):
            return RESTDictError({self._map_key(key): val for key, val in self.data.items()})
        elif isinstance(self.data, RESTListError):
            return RESTListError([LazyMappedSerializedData(val, self.data_mapping) for val in self.data])
        elif isinstance(self.data, RESTDictIndexError):
            return RESTDictIndexError(
                self.data.index,
                {self._map_key(key): val for key, val in self.data.data.items()}
            )
        elif isinstance(self.data, (types.GeneratorType, list, tuple)):
            return [LazyMappedSerializedData(val, self.data_mapping) for val in self.data]
        elif isinstance(self.data, dict):
            return OrderedDict(((self._map_key(key), val) for key, val in self.data.items()))
        else:
            return self.data


LAZY_SERIALIZERS = (LazySerializedData, LazyMappedSerializedData)


class Serializer:
    """
    REST serializer and deserializer, firstly is data serialized to standard python data types and after that is
    used convertor for final serialization
    """

    SERIALIZATION_TYPES = Enum('VERBOSE', 'RAW', 'BOTH')

    def __init__(self, request=None):
        self.request = request

    def _get_serializer(self, data):
        return get_serializer(data, request=self.request)

    def _data_to_python(self, data, serialization_format, lazy=False, **kwargs):
        return self._get_serializer(data).serialize(data, serialization_format, **kwargs)

    def _lazy_data_to_python(self, data, serialization_format, lazy=False, **kwargs):
        if lazy:
            return LazySerializedData(
                self._get_serializer(data), data, serialization_format, lazy=lazy, **kwargs
            )
        else:
            return self._data_to_python(data, serialization_format, lazy=lazy, **kwargs)

    def serialize(self, data, serialization_format, **kwargs):
        raise NotImplementedError

    def deserialize(self, data):
        raise NotImplementedError


class ResourceSerializerMixin:

    def __init__(self, resource, request=None):
        self.resource = resource
        super(ResourceSerializerMixin, self).__init__(request=request)

    def _get_serializer(self, data):
        return get_serializer(data, request=self.request, resource_typemapper=self.resource.resource_typemapper)

    def deserialize(self, data):
        return data

    def _serialize_recursive(self, data, serialization_format, **kwargs):
        if isinstance(data, dict):
            return dict(
                [
                    (k, self._serialize_recursive(v, serialization_format, **kwargs)) for k, v in data.items()
                ]
            )
        elif isinstance(data, (list, tuple, set)):
            return (self._serialize_recursive(v, serialization_format, **kwargs) for v in data)
        else:
            return self._serialize_other(data, serialization_format, **kwargs)

    def _serialize_other(self, data, serialization_format, **kwargs):
        copy_kwargs = kwargs.copy()
        copy_kwargs['via'] = self.resource._get_via(copy_kwargs.get('via'))
        return self._data_to_python(data, serialization_format, **copy_kwargs)

    def serialize(self, data, serialization_format, **kwargs):
        return self._serialize_recursive(data, serialization_format, **kwargs)


class ResourceSerializer(ResourceSerializerMixin, Serializer):

    def _serialize_recursive(self, data, serialization_format, **kwargs):
        if isinstance(data, dict):
            return self.resource.update_serialized_data(
                super(ResourceSerializer, self)._serialize_recursive(data, serialization_format, **kwargs)
            )
        else:
            return super(ResourceSerializer, self)._serialize_recursive(data, serialization_format, **kwargs)


class ObjectResourceSerializer(ResourceSerializerMixin, Serializer):

    def _serialize_recursive(self, data, serialization_format, **kwargs):
        if isinstance(data, self.resource.model):
            if not self.resource.has_read_obj_permission(obj=data, via=kwargs.get('via')):
                raise NotAllowedException
            return self.resource.update_serialized_data(
                data.serialize(serialization_format, request=self.request, **kwargs)
            )
        else:
            return super(ObjectResourceSerializer, self)._serialize_recursive(data, serialization_format, **kwargs)


@register(str)
class StringSerializer(Serializer):

    def serialize(self, data, serialization_format, allow_tags=False, **kwargs):
        serialized_string = force_text(data, strings_only=True)
        return serialized_string if allow_tags or settings.ALLOW_TAGS else conditional_escape(serialized_string)


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


@register(Serializable)
class SerializableSerializer(Serializer):

    def serialize(self, data, serialization_format, **kwargs):
        return data.serialize(serialization_format, request=self.request, **kwargs)


@register((Model, QuerySet, QuerysetIteratorHelper))
class ModelSerializer(Serializer):

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
        elif raw is None:
            return settings.NONE_HUMANIZED_VALUE
        else:
            return raw

    def _value_to_raw_verbose(self, val, field_or_method, obj, **kwargs):
        return RawVerboseValue(val, self._get_verbose_value(val, field_or_method, obj, **kwargs))

    def _method_to_python(self, method, obj, serialization_format, allow_tags=False, **kwargs):
        method_kwargs_names = inspect.getargspec(method)[0][1:]

        method_kwargs = {}

        fun_kwargs = {'request': self.request, 'obj': obj} if self.request else {'obj': obj}

        for arg_name in method_kwargs_names:
            if arg_name in fun_kwargs:
                method_kwargs[arg_name] = fun_kwargs[arg_name]

        if len(method_kwargs_names) == len(method_kwargs):
            return self._data_to_python(
                self._value_to_raw_verbose(method(**method_kwargs), method, obj,
                                           **{k: v for k, v in method_kwargs.items() if k != 'obj'}),
                serialization_format, allow_tags=allow_tags or getattr(method, 'allow_tags', False), **kwargs
            )
        else:
            raise SerializationException('Invalid method parameters')

    def _model_field_to_python(self, field, obj, serialization_format, allow_tags=False, **kwargs):
        return (self._lazy_data_to_python if field.is_relation else self._data_to_python)(
            self._value_to_raw_verbose(self._get_model_field_raw_value(obj, field), field, obj)
            if not field.remote_field else getattr(obj, field.name),
            serialization_format, allow_tags=allow_tags or getattr(field, 'allow_tags', False), **kwargs
        )

    def _m2m_field_to_python(self, field, obj, serialization_format, allow_tags=False, **kwargs):
        return (self._data_to_python(m, serialization_format,
                                     allow_tags=allow_tags or getattr(field, 'allow_tags', False), **kwargs)
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
                         obj, serialization_format, allow_tags=False, **kwargs):

        if field_name == '_obj_name':
            return force_text(obj)
        elif field_name in resource_method_fields:
            return self._method_to_python(resource_method_fields[field_name], obj, serialization_format,
                                          allow_tags=allow_tags, **kwargs)
        elif field_name in m2m_fields:
            return self._m2m_field_to_python(
                m2m_fields[field_name], obj, serialization_format, allow_tags=allow_tags, **kwargs
            )
        elif field_name in model_fields:
            return self._model_field_to_python(
                model_fields[field_name], obj, serialization_format, allow_tags=allow_tags, **kwargs
            )
        else:
            val = getattr(obj, field_name, None) if hasattr(obj, field_name) else None
            if hasattr(val, 'all'):
                return self._reverse_qs_to_python(
                    val, field_name, obj, serialization_format, allow_tags=allow_tags, **kwargs
                )
            elif isinstance(val, Model):
                return self._reverse_to_python(
                    val, field_name, obj, serialization_format, allow_tags=allow_tags, **kwargs
                )
            elif callable(val):
                return self._method_to_python(val, obj, serialization_format, allow_tags=allow_tags, **kwargs)
            else:
                method = get_class_method(obj, field_name)
                return self._data_to_python(
                    self._value_to_raw_verbose(val, method, obj),
                    serialization_format,
                    allow_tags=allow_tags or method is not None and getattr(method, 'allow_tags', False),
                    **kwargs
                )

    def _fields_to_python(self, obj, serialization_format, fieldset, requested_fieldset, **kwargs):
        model_resource = self._get_model_resource(obj)
        resource_method_fields = (
            model_resource.get_methods_returning_field_value(fieldset.flat()) if model_resource else {}
        )
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

    def _get_fieldset_from_resource(self, model_resource, obj, via, has_read_permission):
        if not has_read_permission:
            return model_resource.get_guest_fields_rfs(obj)
        else:
            return model_resource.get_general_fields_rfs(obj)

    def _get_allowed_fieldset_from_resource(self, model_resource, obj, via, has_read_permission):
        if not has_read_permission:
            return model_resource.get_guest_fields_rfs(obj)
        else:
            return model_resource.get_allowed_fields_rfs(obj)

    def _get_direct_serialization_fields(self, obj):
        return rfs(obj._rest_meta.direct_serialization_fields).join(rfs(obj._rest_meta.default_fields))

    def _get_fieldset(self, obj, extended_fieldset, requested_fieldset, exclude_fields, via, direct_serialization,
                      serialized_objects):

        if self._get_obj_serialization_name(obj) in serialized_objects:
            return rfs((get_last_parent_pk_field_name(obj),))

        model_resource = self._get_model_resource(obj)

        if model_resource:
            has_read_permission = model_resource.has_read_obj_permission(obj=obj, via=via)
            default_fieldset = self._get_fieldset_from_resource(model_resource, obj, via, has_read_permission)
            allowed_fieldset = self._get_allowed_fieldset_from_resource(model_resource, obj, via, has_read_permission)
        else:
            direct_serialization_fields = self._get_direct_serialization_fields(obj)
            allowed_fieldset = rfs(
                requested_fieldset if requested_fieldset else (
                    direct_serialization_fields if direct_serialization else obj._rest_meta.guest_fields
                )
            )
            default_fieldset = rfs(direct_serialization_fields if direct_serialization else obj._rest_meta.guest_fields)

        if extended_fieldset:
            default_fieldset.join(extended_fieldset)
            allowed_fieldset.join(extended_fieldset)

        if requested_fieldset:
            # requested_fieldset must be cloned because RFS is not immutable and intersection change it
            fieldset = rfs(requested_fieldset).intersection(allowed_fieldset)
        else:
            fieldset = default_fieldset.intersection(allowed_fieldset)

        if exclude_fields:
            fieldset.subtract(exclude_fields)
        return fieldset

    def _get_obj_serialization_name(self, obj):
        return '{}__{}'.format(obj._meta.db_table, obj.pk)

    def _obj_to_python(self, obj, serialization_format, requested_fieldset=None, extended_fieldset=None,
                       exclude_fields=None, direct_serialization=False,
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

    def _serialize_recursive(self, data, serialization_format, **kwargs):
        if (isinstance(data, self.resource.model) or
              isinstance(data, (QuerysetIteratorHelper, QuerySet)) and issubclass(data.model, self.resource.model)):
            return self.resource.update_serialized_data(
                ModelSerializer.serialize(self, data, serialization_format, **kwargs)
            )
        else:
            return super(ModelResourceSerializer, self)._serialize_recursive(data, serialization_format, **kwargs)


def serialize(data, requested_fieldset=None, serialization_format=Serializer.SERIALIZATION_TYPES.RAW,
              converter_name=None, allow_tags=None):
    from pyston.converters import get_default_converter_name

    converter_name = converter_name if converter_name is not None else get_default_converter_name()
    try:
        converter = get_converter(converter_name) if converter_name != 'python' else None
    except ValueError:
        raise UnsupportedMediaTypeException

    requested_fieldset = rfs(requested_fieldset) if requested_fieldset is not None else None
    converted_dict = get_serializer(data).serialize(
        data, serialization_format, requested_fieldset=requested_fieldset, direct_serialization=True,
        allow_tags=allow_tags or (converter and converter.allow_tags)
    )
    if converter:
        os = UniversalBytesIO()
        converter.encode_to_stream(os, converted_dict)
        return os.get_string_value()
    else:
        return serialized_data_to_python(converted_dict)
