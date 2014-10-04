import decimal
import datetime
import inspect

from django.conf import settings
from django.utils.encoding import force_text
from django.db.models import Model
from django.db.models.query import QuerySet
from django.db.models.fields.files import FileField
from django.utils import formats, timezone
from django.utils.translation import ugettext as _
from django.db.models.fields.related import ForeignRelatedObjectsDescriptor, SingleRelatedObjectDescriptor

from .exception import MimerDataException, UnsupportedMediaTypeException
from .utils import coerce_put_post, list_to_dict, dict_to_list, Enum
from .converter import converters, get_converter

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
    SERIALIZATION_TYPES = Enum(('VERBOSE', 'RAW', 'BOTH'))

    def _get_resource(self, obj):
        from .resource import typemapper

        resource_class = typemapper.get(type(obj))
        if resource_class:
            return resource_class()

    def get_serialization_format(self, request):
        serialization_format = request.META.get('HTTP_X_SERIALIZATION_FORMAT', self.SERIALIZATION_TYPES.RAW)
        if serialization_format not in self.SERIALIZATION_TYPES:
            return self.SERIALIZATION_TYPES.RAW
        return serialization_format

    def serialize_chain(self, request, thing, format, **kwargs):
        if not hasattr(thing, '_resource'):
            resource = self._get_resource(thing)
            if resource:
                thing._resource = resource
                kwargs['via'] = via = list(kwargs.get('via', []))
                via.append(resource)
                return resource.serializer(resource).serialize_to_dict(request, thing, format, **kwargs)

        for serializer in value_serializers:
            if serializer.can_serialize(thing):
                return serializer.serialize_to_dict(request, thing, format, **kwargs)
        raise ValueError('Not found serializer for %s' % thing)

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return self.serialize_chain(request, thing, format, **kwargs)

    def can_serialize(self, thing):
        raise NotImplementedError


class ResourceSerializer(Serializer):

    def __init__(self, resource):
        self.resource = resource

    def determine_convertor(self, request, input=False):
        """
        Method for determening which convertor to use
        for output. It lives here so you can easily subclass
        `Resource` in order to change how emission is detected.
        """
        try:
            import mimeparse
        except ImportError:
            mimeparse = None

        default_convertor = getattr(settings, 'PISTON_DEFAULT_CONVERTOR', 'json')

        header_name = 'HTTP_ACCEPT'
        if input:
            header_name = 'CONTENT_TYPE'

        if mimeparse and header_name in request.META:
            supported_mime_types = set()
            convertor_map = {}
            preferred_content_type = None
            for name, (_, content_type) in converters.items():
                content_type_without_encoding = content_type.split(';')[0]
                if default_convertor and name == default_convertor:
                    preferred_content_type = content_type_without_encoding
                supported_mime_types.add(content_type_without_encoding)
                convertor_map[content_type_without_encoding] = name
            supported_mime_types = list(supported_mime_types)
            if preferred_content_type:
                supported_mime_types.append(preferred_content_type)
            try:
                preferred_content_type = mimeparse.best_match(supported_mime_types,
                                                              request.META[header_name])
            except ValueError:
                pass
            return convertor_map.get(preferred_content_type, default_convertor)
        return default_convertor

    def serialize(self, request, result, fields):

        converted_dict = self.serialize_to_dict(request, result, self.get_serialization_format(request), fields=fields)

        converter, ct = get_converter(self.determine_convertor(request))
        return converter().encode(request, converted_dict, self.resource, result, fields), ct

    def deserialize(self, request):
        rm = request.method.upper()

        # Django's internal mechanism doesn't pick up
        # PUT request, so we trick it a little here.
        if rm == "PUT":
            coerce_put_post(request)

        if rm in ('POST', 'PUT'):
            try:
                converter, ct = get_converter(self.determine_convertor(request, True))
                request.data = converter().decode(request, request.body)
            except (TypeError, ValueError):
                raise MimerDataException
            except NotImplementedError:
                raise UnsupportedMediaTypeException
        return request


@register
class StringSerializer(Serializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return force_text(thing, strings_only=True)

    def can_serialize(self, thing):
        return True


@register
class DictSerializer(Serializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return dict([(k, self.serialize_chain(request, v, format, **kwargs)) for k, v in thing.iteritems()])

    def can_serialize(self, thing):
        return isinstance(thing, dict)


@register
class ListSerializer(Serializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return [self.serialize_chain(request, v, format, **kwargs) for v in thing]

    def can_serialize(self, thing):
        return isinstance(thing, (list, tuple, set, QuerySet))


@register
class DecimalSerializer(Serializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return str(thing)

    def can_serialize(self, thing):
        return isinstance(thing, decimal.Decimal)


@register
class RawVerboseSerializer(Serializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return self.serialize_chain(request, thing.get_value(format), format, **kwargs)

    def can_serialize(self, thing):
        return isinstance(thing, RawVerboseValue)


@register
class ModelSerializer(Serializer):

    RESERVED_FIELDS = set([ 'read', 'update', 'create',
                            'delete', 'model',
                            'allowed_methods', 'fields', 'exclude' ])

    def _get_fields(self, request, obj, fields, exclude_fields, via):
        if not fields:
            resource = self._get_model_resource(obj)
            if (not resource.has_read_permission(request, obj, via) and
                not resource.has_update_permission(request, obj, via) and
                not resource.has_create_permission(request, obj, via)):
                fields = resource.get_guest_fields(request)
            else:
                fields = resource.get_default_obj_fields(request, obj)

        # Remove exclude fields from serialized fields
        fields = list_to_dict(fields)
        for exclude_field in exclude_fields:
            fields.pop(exclude_field, None)
        return set(dict_to_list(fields))

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

    def _serialize_method(self, method, request, obj, format, **kwargs):
        method_kwargs_names = inspect.getargspec(method)[0][1:]

        method_kwargs = {}
        fun_kwargs = {'request': request, 'obj': obj}

        for arg_name in method_kwargs_names:
            if arg_name in fun_kwargs:
                method_kwargs[arg_name] = fun_kwargs[arg_name]

        if len(method_kwargs_names) == len(method_kwargs):
            return self.serialize_chain(request, method(**method_kwargs), format, **kwargs)

    def _serialize_model_field(self, field, request, obj, format, **kwargs):
        if not field.rel:
            val = self._get_model_value(obj, field)
        else:
            val = getattr(obj, field.name)
        return self.serialize_chain(request, val, format, **kwargs)

    def _serialize_m2m_field(self, field, request, obj, format, **kwargs):
        return [self.serialize_chain(request, m, format, **kwargs) for m in getattr(obj, field.name).iterator()]

    def _serialize_reverse_qs(self, val, request, obj, format, **kwargs):
        return [self.serialize_chain(request, m, format, **kwargs) for m in val.iterator()]

    def _serialize_reverse(self, val, field, request, obj, format, **kwargs):
        model = val.__class__
        exclude_fields = []
        if hasattr(model, field) and isinstance(getattr(model, field, None),
                                                            (ForeignRelatedObjectsDescriptor,
                                                            SingleRelatedObjectDescriptor)):
            exclude_fields.append(getattr(model, field).related.field.name)
        return self.serialize_chain(request, val, format, exclude_fields=exclude_fields, **kwargs)

    def _copy_kwargs(self, kwargs):
        subkwargs = kwargs.copy()
        subkwargs['exclude_fields'] = None
        return subkwargs

    def _get_field_name(self, field, subkwargs):
        if isinstance(field, (list, tuple)):
            field, subkwargs['fields'] = field
        else:
            field, subkwargs['fields'] = field, None
        return field

    def _serialize_fields(self, request, obj, format, fields, **kwargs):
        resource_method_fields = self._get_resource_method_fields(self._get_model_resource(obj), fields)
        model_fields = self._get_model_fields(obj)
        m2m_fields = self._get_m2m_fields(obj)

        out = dict()
        for field in fields:
            subkwargs = self._copy_kwargs(kwargs)
            field = self._get_field_name(field, subkwargs)

            if field in resource_method_fields:
                out[field] = self._serialize_method(resource_method_fields[field], request, obj, format, **subkwargs)
            elif field in model_fields:
                out[field] = self._serialize_model_field(model_fields[field], request, obj, format, **subkwargs)
            elif field in m2m_fields:
                out[field] = self._serialize_m2m_field(m2m_fields[field], request, obj, format, **subkwargs)
            else:
                try:
                    val = getattr(obj, field, None)
                    if hasattr(val, 'all'):
                        out[field] = self._serialize_reverse_qs(val, request, obj, format, **subkwargs)
                    elif callable(val):
                        out[field] = self._serialize_method(val, request, obj, format, **subkwargs)
                    elif isinstance(val, Model):
                        out[field] = self._serialize_reverse(val, field, request, obj, format, **subkwargs)
                    else:
                        out[field] = self.serialize_chain(request, val, format, **kwargs)
                except:
                    val = None


        return out

    def _get_model_value(self, obj, field):
        raw = self._get_model_field_raw_value(obj, field)
        verbose = self._get_model_field_verbose_value(obj, field)
        return RawVerboseValue(raw, verbose)

    def _get_model_field_raw_value(self, obj, field):
        val = getattr(obj, field.attname)
        if isinstance(field, FileField) and val:
            val = val.url
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

    def _get_model_resource(self, obj):
        from .resource import DefaultRestModelResource

        if hasattr(obj, '_resource'):
            return obj._resource
        else:
            return DefaultRestModelResource()

    def serialize_to_dict(self, request, obj, format, fields=None, exclude_fields=None, **kwargs):
        exclude_fields = exclude_fields or []
        fields = self._get_fields(request, obj, fields, exclude_fields, kwargs.get('via', []))
        return self._serialize_fields(request, obj, format, fields, **kwargs)

    def can_serialize(self, thing):
        return isinstance(thing, Model)


'''value_serializers = [RawVerboseSerializer(), DictSerializer(), ListSerializer(), DecimalSerializer(), ModelSerializer(),
                     StringSerializer()]'''
