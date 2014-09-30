import decimal
import datetime
import inspect

from django.conf import settings

from .utils import coerce_put_post
from .mimers import translate_mime
from django.utils.encoding import force_text
from piston.emitters import RawVerboseValue
from django.db.models import Model
from piston.utils import list_to_dict, dict_to_list, Enum
from django.db.models.query import QuerySet
from django.db.models.fields.files import FileField
from django.utils import formats, timezone
from django.utils.translation import ugettext as _
from django.db.models.fields.related import ForeignRelatedObjectsDescriptor, SingleRelatedObjectDescriptor
from piston.converter import Converter


def determine_convertor(request, default_convertor=None):
    """
    Function for determening which convertor to use
    for output. It lives here so you can easily subclass
    `Resource` in order to change how emission is detected.
    """
    try:
        import mimeparse
    except ImportError:
        mimeparse = None

    default_convertor = default_convertor or getattr(settings, 'PISTON_DEFAULT_CONVERTOR', 'json')

    if mimeparse and 'HTTP_ACCEPT' in request.META:
        supported_mime_types = set()
        convertor_map = {}
        preferred_content_type = None
        for name, (_, content_type) in Converter.CONVERTERS.items():
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
                                                     request.META['HTTP_ACCEPT'])
        except ValueError:
            pass
        return convertor_map.get(preferred_content_type, default_convertor)
    return default_convertor


class DefaultSerializer(object):

    def __init__(self, resource):
        self.resource = resource

    def deserialize(self, request):
        return ValueSerializer().deserialize(request)

    def serialize(self, request, result, fields):
        return ValueSerializer().serialize(request, self.resource, result, fields=fields)


class ValueSerializer(object):

    RESERVED_FIELDS = set([ 'read', 'update', 'create',
                            'delete', 'model',
                            'allowed_methods', 'fields', 'exclude' ])

    SERIALIZATION_TYPES = Enum(('VERBOSE', 'RAW', 'BOTH'))

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
            for name, (_, content_type) in Converter.CONVERTERS.items():
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

    def get_serialization_format(self, request):
        serialization_format = request.META.get('HTTP_X_SERIALIZATION_FORMAT', self.SERIALIZATION_TYPES.RAW)
        if serialization_format not in self.SERIALIZATION_TYPES:
            return self.SERIALIZATION_TYPES.RAW
        return serialization_format

    def serialize_chain(self, request, thing, format, **kwargs):
        for serializer in value_serializers:
            if serializer.can_serialize(thing):
                return serializer.serialize_to_dict(request, thing, format, **kwargs)
        raise ValueError('Not found serializer for %s' % thing)

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return self.serialize_chain(request, thing, format, **kwargs)

    def serialize(self, request, resource, result, **kwargs):

        converted_dict = self.serialize_to_dict(request, result, self.get_serialization_format(request), **kwargs)

        converter, ct = Converter.get(self.determine_convertor(request))
        return converter().encode(request, converted_dict, resource, result), ct

    def deserialize(self, request):
        rm = request.method.upper()

        # Django's internal mechanism doesn't pick up
        # PUT request, so we trick it a little here.
        if rm == "PUT":
            coerce_put_post(request)

        if rm in ('POST', 'PUT'):
            converter, ct = Converter.get(self.determine_convertor(request, True))
            request.data = converter().decode(request, request.body)
        return request

    def can_serialize(self, thing):
        raise NotImplementedError


class StringSerializer(ValueSerializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return force_text(thing, strings_only=True)

    def can_serialize(self, thing):
        return True


class RawVerboseValueSerializer(ValueSerializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return self.serialize_chain(request, thing.get_value(format), format, **kwargs)

    def can_serialize(self, thing):
        return isinstance(thing, RawVerboseValue)


class DictSerializer(ValueSerializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return dict([(k, self.serialize_chain(request, v, format, **kwargs)) for k, v in thing.iteritems()])

    def can_serialize(self, thing):
        return isinstance(thing, dict)


class ListSerializer(ValueSerializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return [self.serialize_chain(request, v, format, **kwargs) for v in thing]

    def can_serialize(self, thing):
        return isinstance(thing, (list, tuple, set, QuerySet))


class DecimalSerializer(ValueSerializer):

    def serialize_to_dict(self, request, thing, format, **kwargs):
        return str(thing)

    def can_serialize(self, thing):
        return isinstance(thing, decimal.Decimal)


class ModelSerializer(ValueSerializer):

    def _get_fields(self, request, obj, fields, exclude_fields, via):
        if not fields:
            if (not obj._resource.has_read_permission(request, obj, via) and
                not obj._resource.has_update_permission(request, obj, via) and
                not obj._resource.has_create_permission(request, obj, via)):
                fields = obj._resource.get_guest_fields(request)
            else:
                fields = obj._resource.get_default_obj_fields(request, obj)

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
            val = self._get_value(obj, field)
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

    def _serialize_fields(self, request, obj, format, fields, **kwargs):
        resource_method_fields = self._get_resource_method_fields(obj._resource, fields)
        model_fields = self._get_model_fields(obj)
        m2m_fields = self._get_m2m_fields(obj)

        out = dict()
        for field in fields:
            subkwargs = kwargs.copy()
            subkwargs['exclude_fields'] = None
            if isinstance(field, (list, tuple)):
                field, subkwargs['fields'] = field
            else:
                field, subkwargs['fields'] = field, None

            val = None
            if field in resource_method_fields:
                val = self._serialize_method(resource_method_fields[field], request, obj, format, **subkwargs)
            elif field in model_fields:
                val = self._serialize_model_field(model_fields[field], request, obj, format, **subkwargs)
            elif field in m2m_fields:
                val = self._serialize_m2m_field(m2m_fields[field], request, obj, format, **subkwargs)
            else:
                try:
                    val = getattr(obj, field, None)
                except:
                    val = None

                if hasattr(val, 'all'):
                    val = self._serialize_reverse_qs(val, request, obj, format, **subkwargs)
                elif callable(val):
                    val = self._serialize_method(val, request, obj, format, **subkwargs)
                elif isinstance(val, Model):
                    val = self._serialize_reverse(val, field, request, obj, format, **subkwargs)
                else:
                    val = self.serialize_chain(request, val, format, **kwargs)

            if val:
                out[field] = val

        return out

    def _get_value(self, obj, field):
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

    def serialize_to_dict(self, request, obj, format, fields=None, exclude_fields=None, **kwargs):
        exclude_fields = exclude_fields or []

        fields = self._get_fields(request, obj, fields, exclude_fields, kwargs.get('via', []))
        return self._serialize_fields(request, obj, format, fields, **kwargs)

    def can_serialize(self, thing):
        return isinstance(thing, Model)


class ModelResourceSerializer(ValueSerializer):

    def _get_resource(self, obj):
        from .resource import DefaultRestModelResource
        from piston.resource import typemapper

        return (typemapper.get(type(obj)) or DefaultRestModelResource)()

    def serialize_to_dict(self, request, obj, format, via=None, **kwargs):
        via = via or []
        obj._resource = self._get_resource(obj)
        via.append(obj._resource)
        return self.serialize_chain(request, obj, format, via=via, **kwargs)

    def can_serialize(self, thing):
        return isinstance(thing, Model) and not hasattr(thing, '_resource')


value_serializers = [ModelResourceSerializer(), RawVerboseValueSerializer(), DictSerializer(), ListSerializer(), DecimalSerializer(), ModelSerializer(), StringSerializer()]
