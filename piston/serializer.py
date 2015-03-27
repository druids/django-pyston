import decimal
import datetime
import inspect

from django.db.models import Model
from django.db.models.query import QuerySet
from django.db.models.fields.files import FileField
from django.db.models.fields.related import ForeignRelatedObjectsDescriptor, SingleRelatedObjectDescriptor
from django.utils import formats, timezone
from django.utils.encoding import force_text
from django.utils.translation import ugettext as _

from chamber.utils.datastructures import Enum

from .exception import MimerDataException, UnsupportedMediaTypeException
from .utils import coerce_put_post
from .converter import get_converter_from_request
from .converter.datastructures import ModelSortedDict
from piston.utils import rfs


value_serializers = []


def register(klass):
    """
    Adds throttling validator to a class.
    """
    for serializer in value_serializers:
        if type(serializer) == klass:
            return None
    value_serializers.insert(0, klass())
    return klass


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


class Serializer(object):
    """
    REST serializer and deserializer, firstly is data serialized to standard python data types and after that is
    used convertor for final serialization
    """

    SERIALIZATION_TYPES = Enum('VERBOSE', 'RAW', 'BOTH')

    def _get_resource(self, request, obj):
        from .resource import typemapper

        resource_class = typemapper.get(type(obj))
        if resource_class:
            return resource_class(request)

    def _to_python_via_resource(self, request, thing, serialization_format, **kwargs):
        resource = self._get_resource(request, thing)
        if resource:
            thing._resource = resource
            return resource.serializer(resource)._to_python(request, thing, serialization_format, **kwargs)
        else:
            return None

    def _find_to_serializer(self, thing):
        for serializer in value_serializers:
            if serializer._can_transform_to_python(thing):
                return serializer

    def _to_python_chain(self, request, thing, serialization_format, **kwargs):
        if not hasattr(thing, '_resource'):
            result = self._to_python_via_resource(request, thing, serialization_format, **kwargs)
            if result:
                return result
        serializer = self._find_to_serializer(thing)
        if serializer:
            return serializer._to_python(request, thing, serialization_format, **kwargs)
        raise NotImplementedError('Serializer not found for %s' % thing)

    def _to_python(self, request, thing, serialization_format, **kwargs):
        return self._to_python_chain(request, thing, serialization_format, **kwargs)

    def _can_transform_to_python(self, thing):
        raise NotImplementedError


class ResourceSerializer(Serializer):
    """
    Default resource serializer perform serialization to th client format
    """

    def __init__(self, resource):
        self.resource = resource

    def serialize(self, request, result, requested_fieldset, serialization_format):
        detailed = self.resource._is_single_obj_request(result)
        converted_dict = self._to_python(request, result, serialization_format,
                                         requested_fieldset=requested_fieldset,
                                         detailed=detailed)
        try:
            converter, ct = get_converter_from_request(request)
        except ValueError:
            raise UnsupportedMediaTypeException

        return converter().encode(request, converted_dict, self.resource, result), ct

    def deserialize(self, request):
        rm = request.method.upper()
        # Django's internal mechanism doesn't pick up
        # PUT request, so we trick it a little here.
        if rm == "PUT":
            coerce_put_post(request)

        if rm in ('POST', 'PUT'):
            try:
                converter, _ = get_converter_from_request(request, True)
                request.data = converter().decode(request, request.body)
            except (TypeError, ValueError):
                raise MimerDataException
            except NotImplementedError:
                raise UnsupportedMediaTypeException
        return request

    def _to_python(self, request, thing, serialization_format, **kwargs):
        return super(ResourceSerializer, self)._to_python(request, thing, serialization_format, **kwargs)


@register
class StringSerializer(Serializer):

    def _to_python(self, request, thing, serialization_format, **kwargs):
        return force_text(thing, strings_only=True)

    def _can_transform_to_python(self, thing):
        return True


@register
class DictSerializer(Serializer):

    def _to_python(self, request, thing, serialization_format, requested_fieldset=None,
                   extended_fieldset=None, detailed=False, exclude_fields=None, **kwargs):
        return dict([(k, self._to_python_chain(request, v, serialization_format, **kwargs))
                     for k, v in thing.iteritems()])

    def _can_transform_to_python(self, thing):
        return isinstance(thing, dict)


@register
class ListSerializer(Serializer):

    def _to_python(self, request, thing, serialization_format, requested_fieldset=None,
                   extended_fieldset=None, detailed=False, exclude_fields=None, **kwargs):
        return [self._to_python_chain(request, v, serialization_format, **kwargs) for v in thing]

    def _can_transform_to_python(self, thing):
        return isinstance(thing, (list, tuple, set))


@register
class QuerySetSerializer(Serializer):

    def _to_python(self, request, thing, serialization_format, **kwargs):
        return [self._to_python_chain(request, v, serialization_format, **kwargs) for v in thing]

    def _can_transform_to_python(self, thing):
        return isinstance(thing, QuerySet)


@register
class DecimalSerializer(Serializer):

    def _to_python(self, request, thing, serialization_format, **kwargs):
        return thing

    def _can_transform_to_python(self, thing):
        return isinstance(thing, decimal.Decimal)


@register
class RawVerboseSerializer(Serializer):

    def _to_python(self, request, thing, serialization_format, **kwargs):
        return self._to_python_chain(request, thing.get_value(serialization_format), serialization_format, **kwargs)

    def _can_transform_to_python(self, thing):
        return isinstance(thing, RawVerboseValue)


@register
class ModelSerializer(Serializer):

    RESERVED_FIELDS = {'read', 'update', 'create', 'delete', 'model', 'allowed_methods', 'fields', 'exclude'}

    def _get_resource_method_fields(self, resource, fields):
        out = dict()
        # TODO
        for field in fields.flat() - self.RESERVED_FIELDS:
            t = getattr(resource, str(field), None)
            if t and callable(t):
                out[field] = t
        return out

    def _get_model_fields(self, obj):
        out = dict()
        for f in obj._meta.fields:
            if hasattr(f, 'serialize') and f.serialize:
                out[f.name] = f
        return out

    def _get_m2m_fields(self, obj):
        out = dict()
        for mf in obj._meta.many_to_many:
            if mf.serialize:
                out[mf.name] = mf
        return out

    def _method_to_python(self, method, request, obj, serialization_format, **kwargs):
        method_kwargs_names = inspect.getargspec(method)[0][1:]

        method_kwargs = {}
        fun_kwargs = {'request': request, 'obj': obj}

        for arg_name in method_kwargs_names:
            if arg_name in fun_kwargs:
                method_kwargs[arg_name] = fun_kwargs[arg_name]

        if len(method_kwargs_names) == len(method_kwargs):
            return self._to_python_chain(request, method(**method_kwargs), serialization_format, **kwargs)

    def _model_field_to_python(self, field, request, obj, serialization_format, **kwargs):
        if not field.rel:
            val = self._get_model_value(obj, field)
        else:
            val = getattr(obj, field.name)
        return self._to_python_chain(request, val, serialization_format, **kwargs)

    def _m2m_field_to_python(self, field, request, obj, serialization_format, **kwargs):
        return [self._to_python_chain(request, m, serialization_format, **kwargs)
                for m in getattr(obj, field.name).all()]

    def _get_reverse_excluded_fields(self, field, obj):
        model = obj.__class__
        exclude_fields = []
        if hasattr(model, field) and isinstance(getattr(model, field, None),
                                                            (ForeignRelatedObjectsDescriptor,
                                                            SingleRelatedObjectDescriptor)):
            exclude_fields.append(getattr(model, field).related.field.name)
        return exclude_fields

    def _reverse_qs_to_python(self, val, field, request, obj, serialization_format, **kwargs):
        kwargs['exclude_fields'] = self._get_reverse_excluded_fields(field, obj)
        return [self._to_python_chain(request, m, serialization_format, **kwargs) for m in val.all()]

    def _reverse_to_python(self, val, field, request, obj, serialization_format, **kwargs):
        kwargs['exclude_fields'] = self._get_reverse_excluded_fields(field, obj)
        return self._to_python_chain(request, val, serialization_format, **kwargs)

    def _copy_kwargs(self, resource, kwargs):
        subkwargs = kwargs.copy()
        subkwargs['exclude_fields'] = None
        subkwargs['via'] = resource._get_via(kwargs.get('via'))
        return subkwargs

    def _get_field_name(self, field, requested_field, subkwargs):
        if field.subfieldset:
            field_name, subkwargs['extended_fieldset'] = field.name, field.subfieldset
        else:
            field_name, subkwargs['extended_fieldset'] = field.name, None

        if requested_field and requested_field.subfieldset:
            subkwargs['requested_fieldset'] = requested_field.subfieldset
        return field_name

    def _get_model_value(self, obj, field):
        raw = self._get_model_field_raw_value(obj, field)
        verbose = self._get_model_field_verbose_value(obj, field)
        return RawVerboseValue(raw, verbose)

    def _get_model_field_raw_value(self, obj, field):
        val = getattr(obj, field.attname)
        if isinstance(field, FileField):
            # FileField returns blank string if file does not exists, None is better
            val = val and val.url or None
        return val

    def _get_model_field_verbose_value(self, obj, field):
        humanize_method_name = 'get_%s_humanized' % field.attname
        if hasattr(getattr(obj, humanize_method_name, None), '__call__'):
            return getattr(obj, humanize_method_name)()
        val = self._get_model_field_raw_value(obj, field)
        if isinstance(val, bool):
            val = val and _('yes') or _('no')
        elif field.choices:
            val = getattr(obj, 'get_%s_display' % field.attname)()
        elif isinstance(val, datetime.datetime):
            return formats.localize(timezone.template_localtime(val))
        elif isinstance(val, (datetime.date, datetime.time)):
            return formats.localize(val)
        return val

    def _field_to_python(self, field_name, resource_method_fields, model_fields, m2m_fields,
                         request, obj, serialization_format, **kwargs):
        if field_name in resource_method_fields:
            return self._method_to_python(resource_method_fields[field_name], request, obj, serialization_format,
                                          **kwargs)
        elif field_name in model_fields:
            return self._model_field_to_python(model_fields[field_name], request, obj, serialization_format, **kwargs)
        elif field_name in m2m_fields:
            return self._m2m_field_to_python(m2m_fields[field_name], request, obj, serialization_format, **kwargs)
        else:
            try:
                val = getattr(obj, field_name, None)
                if hasattr(val, 'all'):
                    return self._reverse_qs_to_python(val, field_name, request, obj, serialization_format, **kwargs)
                elif callable(val):
                    return self._method_to_python(val, request, obj, serialization_format, **kwargs)
                elif isinstance(val, Model):
                    return self._reverse_to_python(val, field_name, request, obj, serialization_format, **kwargs)
                else:
                    return self._to_python_chain(request, val, serialization_format, **kwargs)
            except:
                return None

    def _fields_to_python(self, request, obj, serialization_format, fieldset, requested_fieldset, **kwargs):
        resource_method_fields = self._get_resource_method_fields(self._get_model_resource(request, obj), fieldset)
        model_fields = self._get_model_fields(obj)
        m2m_fields = self._get_m2m_fields(obj)

        out = ModelSortedDict(obj, self._get_model_resource(request, obj))
        for field in fieldset.fields:
            subkwargs = self._copy_kwargs(self._get_model_resource(request, obj), kwargs)
            requested_field = None
            if requested_fieldset:
                requested_field = requested_fieldset.get(field.name)
            field_name = self._get_field_name(field, requested_field, subkwargs)
            out[field_name] = self._field_to_python(
                field_name, resource_method_fields, model_fields, m2m_fields, request, obj, serialization_format,
                **subkwargs
            )

        return out

    def _get_model_resource(self, request, obj):
        from .resource import DefaultRestObjectResource

        if hasattr(obj, '_resource'):
            return obj._resource
        else:
            return DefaultRestObjectResource()

    def _get_fieldset_from_resource(self, request, obj, via, detailed, has_get_permission):
        resource = self._get_model_resource(request, obj)
        if not has_get_permission:
            return resource.get_guest_fields(request)
        elif detailed:
            return resource.get_default_detailed_fields(obj)
        else:
            return resource.get_default_general_fields(obj)

    def _get_allowed_fieldset_from_resource(self, request, obj, via, has_get_permission):
        resource = self._get_model_resource(request, obj)
        if not has_get_permission:
            return resource.get_guest_fields(request)
        else:
            return resource.get_fields(obj)

    def _get_fieldset(self, request, obj, extended_fieldset, requested_fieldset, exclude_fields, via, detailed):
        has_get_permission = (self._get_model_resource(request, obj).has_get_permission(obj, via) or
                              self._get_model_resource(request, obj).has_post_permission(obj, via) or
                              self._get_model_resource(request, obj).has_put_permission(obj, via))
        default_fieldset = self._get_fieldset_from_resource(request, obj, via, detailed, has_get_permission)
        allowed_fieldset = self._get_allowed_fieldset_from_resource(request, obj, via, has_get_permission)

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

    def _to_python(self, request, obj, serialization_format, requested_fieldset=None,
                   extended_fieldset=None, detailed=False, exclude_fields=None, **kwargs):
        exclude_fields = exclude_fields or []
        fieldset = self._get_fieldset(request, obj, extended_fieldset, requested_fieldset, exclude_fields,
                                      kwargs.get('via'), detailed)
        return self._fields_to_python(request, obj, serialization_format, fieldset, requested_fieldset, **kwargs)

    def _can_transform_to_python(self, thing):
        return isinstance(thing, Model)
