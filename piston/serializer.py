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

from .exception import MimerDataException, UnsupportedMediaTypeException
from .utils import coerce_put_post, list_to_dict, dict_to_list, Enum
from .converter import get_converter_from_request

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

    SERIALIZATION_TYPES = Enum(('VERBOSE', 'RAW', 'BOTH'))

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

    def serialize(self, request, result, fields, serialization_format):
        converted_dict = self._to_python(request, result, serialization_format, fields=fields)
        try:
            converter, ct = get_converter_from_request(request)
        except ValueError as ex:
            raise UnsupportedMediaTypeException
        return converter().encode(request, converted_dict, self.resource, result, fields), ct

    def deserialize(self, request):
        rm = request.method.upper()
        # Django's internal mechanism doesn't pick up
        # PUT request, so we trick it a little here.
        if rm == "PUT":
            coerce_put_post(request)

        if rm in ('POST', 'PUT'):
            try:
                converter, ct = get_converter_from_request(request, True)
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

    def _to_python(self, request, thing, serialization_format, fields=None, exclude_fields=None, **kwargs):
        return dict([(k, self._to_python_chain(request, v, serialization_format, **kwargs))
                     for k, v in thing.iteritems()])

    def _can_transform_to_python(self, thing):
        return isinstance(thing, dict)


@register
class ListSerializer(Serializer):

    def _to_python(self, request, thing, serialization_format, fields=None, exclude_fields=None, **kwargs):
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
        return str(thing)

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
        for field in fields - self.RESERVED_FIELDS:
            t = getattr(resource, str(field), None)
            if t and callable(t):
                out[field] = t
        return out

    def _get_model_fields(self, obj):
        out = dict()
        proxy_local_fields = obj._meta.proxy_for_model._meta.local_fields if obj._meta.proxy_for_model else []
        local_fields = obj._meta.local_fields + obj._meta.virtual_fields + proxy_local_fields
        for f in local_fields:
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
                for m in getattr(obj, field.name).iterator()]

    def _reverse_qs_to_python(self, val, request, obj, serialization_format, **kwargs):
        return [self._to_python_chain(request, m, serialization_format, **kwargs) for m in val.iterator()]

    def _reverse_to_python(self, val, field, request, obj, serialization_format, **kwargs):
        model = val.__class__
        exclude_fields = []
        if hasattr(model, field) and isinstance(getattr(model, field, None),
                                                            (ForeignRelatedObjectsDescriptor,
                                                            SingleRelatedObjectDescriptor)):
            exclude_fields.append(getattr(model, field).related.field.name)
        return self._to_python_chain(request, val, serialization_format, exclude_fields=exclude_fields, **kwargs)

    def _copy_kwargs(self, resource, kwargs):
        subkwargs = kwargs.copy()
        subkwargs['exclude_fields'] = None
        subkwargs['via'] = resource._get_via(kwargs.get('via'))
        return subkwargs

    def _get_field_name(self, field, subkwargs):
        if isinstance(field, (list, tuple)):
            field, subkwargs['fields'] = field
        else:
            field, subkwargs['fields'] = field, None
        return field

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
            val = val and _('Yes') or _('No')
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
                    return self._reverse_qs_to_python(val, request, obj, serialization_format, **kwargs)
                elif callable(val):
                    return self._method_to_python(val, request, obj, serialization_format, **kwargs)
                elif isinstance(val, Model):
                    return self._reverse_to_python(val, field_name, request, obj, serialization_format, **kwargs)
                else:
                    return self._to_python_chain(request, val, serialization_format, **kwargs)
            except:
                return None

    def _fields_to_python(self, request, obj, serialization_format, fields, **kwargs):
        resource_method_fields = self._get_resource_method_fields(self._get_model_resource(request, obj), fields)
        model_fields = self._get_model_fields(obj)
        m2m_fields = self._get_m2m_fields(obj)

        out = dict()
        for field in fields:
            subkwargs = self._copy_kwargs(self._get_model_resource(request, obj), kwargs)
            field_name = self._get_field_name(field, subkwargs)
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

    def _get_field_names_from_resource(self, request, obj, via):
        resource = self._get_model_resource(request, obj)
        if (not resource.has_get_permission(obj, via)
            and not resource.has_put_permission(obj, via)
            and not resource.has_post_permission(obj, via)):
            return resource.get_guest_fields(request)
        else:
            return resource.get_default_general_fields(obj)

    def _exclude_field_names(self, fields, exclude_fields):
        field_names = list_to_dict(fields)
        for exclude_field in exclude_fields:
            field_names.pop(exclude_field, None)
        return set(dict_to_list(field_names))

    def _get_field_names(self, request, obj, fields, exclude_fields, via):
        if not fields:
            field_names = self._get_field_names_from_resource(request, obj, via)
        else:
            field_names = list(fields)
        return self._exclude_field_names(field_names, exclude_fields)

    def _to_python(self, request, obj, serialization_format, fields=None, exclude_fields=None, **kwargs):
        exclude_fields = exclude_fields or []
        fields = self._get_field_names(request, obj, fields, exclude_fields, kwargs.get('via'))
        return self._fields_to_python(request, obj, serialization_format, fields, **kwargs)

    def _can_transform_to_python(self, thing):
        return isinstance(thing, Model)
