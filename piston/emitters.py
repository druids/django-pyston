from __future__ import generators, unicode_literals

import datetime, decimal, inspect, json, io

from piston.utils import CsvGenerator, list_to_dict, dict_to_list
from django.db.models.fields.related import ForeignRelatedObjectsDescriptor, SingleRelatedObjectDescriptor


try:
    # yaml isn't standard with python.  It shouldn't be required if it
    # isn't used.
    import yaml
except ImportError:
    yaml = None

# Fallback since `any` isn't in Python <2.5
try:
    any
except NameError:
    def any(iterable):
        for element in iterable:
            if element:
                return True
        return False

from django.db.models.query import QuerySet
from django.db import models
from django.db.models import Model, permalink
from django.utils.xmlutils import SimplerXMLGenerator
from django.utils.encoding import smart_unicode, force_text
from django.core.serializers.json import DateTimeAwareJSONEncoder
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.utils.translation import ugettext as _
from django.utils import formats, timezone
from django.db.models.fields.files import FileField
from django.db.models.fields import FieldDoesNotExist

from .utils import HttpStatusCode, Enum
from .validate_jsonp import is_valid_jsonp_callback_value

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

try:
    import cPickle as pickle
except ImportError:
    import pickle

# Allow people to change the reverser (default `permalink`).
reverser = permalink


class RawVerboseValue(object):

    def __init__(self, raw_value, verbose_value):
        self.raw_value = raw_value
        self.verbose_value = verbose_value

    def get_value(self, serialization_format):
        if serialization_format == Emitter.SERIALIZATION_TYPES.RAW:
            return self.raw_value
        elif serialization_format == Emitter.SERIALIZATION_TYPES.VERBOSE:
            return self.verbose_value
        elif self.raw_value == self.verbose_value:
            return self.raw_value
        else:
            return {'_raw': self.raw_value, '_verbose': self.verbose_value}


class Emitter(object):
    """
    Super emitter. All other emitters should subclass
    this one. It has the `construct` method which
    conveniently returns a serialized `dict`. This is
    usually the only method you want to use in your
    emitter. See below for examples.

    `RESERVED_FIELDS` was introduced when better resource
    method detection came, and we accidentially caught these
    as the methods on the handler. Issue58 says that's no good.
    """
    EMITTERS = { }
    RESERVED_FIELDS = set([ 'read', 'update', 'create',
                            'delete', 'model',
                            'allowed_methods', 'fields', 'exclude' ])

    SERIALIZATION_TYPES = Enum(('VERBOSE', 'RAW', 'BOTH'))

    def __init__(self, payload, typemapper, handler, request, serialization_format, fields=(), fun_kwargs={}):
        self.typemapper = typemapper
        self.data = payload
        self.handler = handler
        self.fields = fields
        self.fun_kwargs = fun_kwargs
        self.request = request
        self.serialization_format = serialization_format

        if isinstance(self.data, Exception):
            raise

    def method_fields(self, handler, fields):
        if not handler:
            return { }

        ret = dict()

        for field in fields - Emitter.RESERVED_FIELDS:
            t = getattr(handler, str(field), None)

            if t and callable(t):
                ret[field] = t

        return ret

    def smart_unicode(self, thing):
        return force_text(thing, strings_only=True)

    def construct(self):
        """
        Recursively serialize a lot of types, and
        in cases where it doesn't recognize the type,
        it will fall back to Django's `smart_unicode`.

        Returns `dict`.
        """
        def _any(thing, fields=None, exclude_fields=None, via=None):
            """
            Dispatch, all types are routed through here.
            """
            ret = None

            if isinstance(thing, RawVerboseValue):
                ret = _raw_verbose(thing, via=via)
            elif isinstance(thing, QuerySet):
                ret = _qs(thing, fields=fields, exclude_fields=exclude_fields, via=via)
            elif isinstance(thing, (tuple, list, set)):
                ret = _list(thing, fields, via=via)
            elif isinstance(thing, dict):
                ret = _dict(thing, fields, via=via)
            elif isinstance(thing, decimal.Decimal):
                ret = str(thing)
            elif isinstance(thing, Model):
                ret = _model(thing, fields=fields, exclude_fields=exclude_fields, via=via)
            elif isinstance(thing, HttpResponse):
                raise HttpStatusCode(thing)
            elif inspect.isfunction(thing):
                if not inspect.getargspec(thing)[0]:
                    ret = _any(thing(), via=via)
            elif hasattr(thing, '__emittable__'):
                f = thing.__emittable__
                if inspect.ismethod(f) and len(inspect.getargspec(f)[0]) == 1:
                    ret = _any(f(), via=via)
            elif repr(thing).startswith("<django.db.models.fields.related.RelatedManager"):
                ret = _any(thing.all(), fields=fields, exclude_fields=exclude_fields, via=via)
            else:
                ret = self.smart_unicode(thing)

            return ret

        def _raw_verbose(data, via=None):
            return _any(data.get_value(self.serialization_format), via=via)

        def _fk(data, field, via=None):
            """
            Foreign keys.
            """
            return _any(getattr(data, field.name), via=via)

        def _related(data, fields=None, via=None):
            """
            Foreign keys.
            """
            return [ _model(m, fields, via=via) for m in data.iterator() ]

        def _m2m(data, field, fields=None, via=None):
            """
            Many to many (re-route to `_model`.)
            """
            return [ _model(m, fields, via=via) for m in getattr(data, field.name).iterator() ]

        def _model_field_raw(data, field):
            val = getattr(data, field.attname)
            if isinstance(field, FileField) and val:
                val = val.url
            return val

        def _model_field_verbose(data, field):
            humanize_method_name = 'get_%s_humanized' % field.attname
            if hasattr(getattr(data, humanize_method_name, None), '__call__'):
                return getattr(data, humanize_method_name)()
            val = _model_field_raw(data, field)
            if isinstance(val, bool):
                val = val and _('Yes') or _('No')
            elif field.choices:
                val = getattr(data, 'get_%s_display' % field.attname)()
            elif isinstance(val, datetime.datetime):
                return formats.localize(timezone.template_localtime(val))
            elif isinstance(val, (datetime.date, datetime.time)):
                return formats.localize(val)
            return val

        def _model(data, fields=None, exclude_fields=None, via=None):
            """
            Models. Will respect the `fields` and/or
            `exclude` on the handler (see `typemapper`.)
            """
            from .resource import DefaultRestModelResource
            ret = { }

            via = via or []
            exclude_fields = exclude_fields or []

            handler = self.in_typemapper(type(data))() or DefaultRestModelResource()

            def v(f):
                raw = _model_field_raw(data, f)
                verbose = _model_field_verbose(data, f)
                return RawVerboseValue(raw, verbose)
            if not fields:
                print handler
                fields = getattr(handler, 'get_default_obj_fields')(self.request, data)
                """
                If user has not read permission only get pid of the object
                """
                # TODO: Better permissions and add method for generation fields to core with request
                if (not handler.has_read_permission(self.request, data, via) and
                    not handler.has_update_permission(self.request, data, via) and
                    not handler.has_create_permission(self.request, data, via)):
                    fields = getattr(handler, 'get_guest_fields')(self.request)

            # Remove exclude fields from serialized fields
            get_fields = list_to_dict(fields)
            for exclude_field in exclude_fields:
                get_fields.pop(exclude_field, None)
            get_fields = set(dict_to_list(get_fields))
            met_fields = self.method_fields(handler, get_fields)

            proxy_local_fields = data._meta.proxy_for_model._meta.local_fields if data._meta.proxy_for_model else []

            for f in data._meta.local_fields + data._meta.virtual_fields + proxy_local_fields:
                if hasattr(f, 'serialize') and f.serialize \
                    and not any([ p in met_fields for p in [ f.attname, f.name ]]):
                    if not f.rel:
                        if f.attname in get_fields:
                            ret[f.attname] = _any(v(f), via=via + [handler])
                            get_fields.remove(f.attname)
                    else:
                        if f.attname[:-3] in get_fields:
                            ret[f.name] = _fk(data, f, via + [handler])
                            get_fields.remove(f.name)

            for mf in data._meta.many_to_many:
                if mf.serialize and mf.attname not in met_fields:
                    if mf.attname in get_fields:
                        ret[mf.name] = _m2m(data, mf, via + [handler])
                        get_fields.remove(mf.name)

            # try to get the remainder of fields
            for maybe_field in get_fields:
                if isinstance(maybe_field, (list, tuple)):
                    model, fields = maybe_field
                    inst = getattr(data, model, None)

                    if inst:
                        if hasattr(inst, 'all'):
                            ret[model] = _related(inst, fields, via + [handler])
                        elif callable(inst):
                            if len(inspect.getargspec(inst)[0]) == 1:
                                ret[model] = _any(inst(), fields, via + [handler])
                        else:
                            ret[model] = _model(inst, fields, via + [handler])

                elif maybe_field in met_fields:
                    # Overriding normal field which has a "resource method"
                    # so you can alter the contents of certain fields without
                    # using different names.
                    ret[maybe_field] = _any(met_fields[maybe_field](data, **self.fun_kwargs), via=via + [handler])

                else:
                    try:
                        maybe = getattr(data, maybe_field, None)
                    except ObjectDoesNotExist:
                        maybe = None
                    if maybe is not None:
                        if callable(maybe):
                            maybe_kwargs_names = inspect.getargspec(maybe)[0][1:]
                            maybe_kwargs = {}

                            for arg_name in maybe_kwargs_names:
                                if arg_name in self.fun_kwargs:
                                    maybe_kwargs[arg_name] = self.fun_kwargs[arg_name]

                            if len(maybe_kwargs_names) == len(maybe_kwargs):
                                ret[maybe_field] = _any(maybe(**maybe_kwargs), via=via + [handler])
                        else:
                            model = data.__class__
                            exclude_fields = []
                            if hasattr(model, maybe_field) and isinstance(getattr(model, maybe_field, None),
                                                                          (ForeignRelatedObjectsDescriptor,
                                                                           SingleRelatedObjectDescriptor)):
                                exclude_fields.append(getattr(model, maybe_field).related.field.name)

                            ret[maybe_field] = _any(maybe, exclude_fields=exclude_fields, via=via + [handler])
                    else:
                        handler_f = getattr(handler or self.handler, maybe_field, None)

                        if handler_f:
                            ret[maybe_field] = _any(handler_f(data, **self.fun_kwargs), via=via + [handler])
            return ret

        def _qs(data, fields=None, exclude_fields=None, via=None):
            """
            Querysets.
            """
            return [ _any(v, fields, exclude_fields, via=via) for v in data ]

        def _list(data, fields=None, via=None):
            """
            Lists.
            """
            return [ _any(v, fields, via=via) for v in data ]

        def _dict(data, fields=None, via=None):
            """
            Dictionaries.
            """
            return dict([ (k, _any(v, fields, via=via)) for k, v in data.iteritems() ])

        # Kickstart the seralizin'.
        return _any(self.data, self.fields)

    def in_typemapper(self, model):
        return self.typemapper.get(model)

    def render(self):
        """
        This super emitter does not implement `render`,
        this is a job for the specific emitter below.
        """
        raise NotImplementedError("Please implement render.")

    def stream_render(self, request, stream=True):
        """
        Tells our patched middleware not to look
        at the contents, and returns a generator
        rather than the buffered string. Should be
        more memory friendly for large datasets.
        """
        yield self.render(request)

    @classmethod
    def get(cls, format):
        """
        Gets an emitter, returns the class and a content-type.
        """
        if cls.EMITTERS.has_key(format):
            return cls.EMITTERS.get(format)

        raise ValueError("No emitters found for type %s" % format)

    @classmethod
    def register(cls, name, klass, content_type='text/plain'):
        """
        Register an emitter.

        Parameters::
         - `name`: The name of the emitter ('json', 'xml', 'yaml', ...)
         - `klass`: The emitter class.
         - `content_type`: The content type to serve response as.
        """
        cls.EMITTERS[name] = (klass, content_type)

    @classmethod
    def unregister(cls, name):
        """
        Remove an emitter from the registry. Useful if you don't
        want to provide output in one of the built-in emitters.
        """
        return cls.EMITTERS.pop(name, None)


class XMLEmitter(Emitter):
    def _to_xml(self, xml, data):
        if isinstance(data, (list, tuple)):
            for item in data:
                xml.startElement("resource", {})
                self._to_xml(xml, item)
                xml.endElement("resource")
        elif isinstance(data, dict):
            for key, value in data.iteritems():
                xml.startElement(key, {})
                self._to_xml(xml, value)
                xml.endElement(key)
        else:
            xml.characters(smart_unicode(data))

    def render(self, request):
        stream = StringIO.StringIO()

        xml = SimplerXMLGenerator(stream, "utf-8")
        xml.startDocument()
        xml.startElement("response", {})

        self._to_xml(xml, self.construct())

        xml.endElement("response")
        xml.endDocument()

        return stream.getvalue()


class JSONEmitter(Emitter):
    """
    JSON emitter, understands timestamps.
    """
    def render(self, request):
        cb = request.GET.get('callback', None)
        seria = json.dumps(self.construct(), cls=DateTimeAwareJSONEncoder, ensure_ascii=False, indent=4)

        # Callback
        if cb and is_valid_jsonp_callback_value(cb):
            return '%s(%s)' % (cb, seria)

        return seria


class YAMLEmitter(Emitter):
    """
    YAML emitter, uses `safe_dump` to omit the
    specific types when outputting to non-Python.
    """
    def render(self, request):
        return yaml.safe_dump(self.construct())


class PickleEmitter(Emitter):
    """
    Emitter that returns Python pickled.
    """
    def render(self, request):
        return pickle.dumps(self.construct())

Emitter.register('pickle', PickleEmitter, 'application/python-pickle')

"""
WARNING: Accepting arbitrary pickled data is a huge security concern.
The unpickler has been disabled by default now, and if you want to use
it, please be aware of what implications it will have.

Read more: http://nadiana.com/python-pickle-insecure

Uncomment the line below to enable it. You're doing so at your own risk.
"""
# Mimer.register(pickle.loads, ('application/python-pickle',))


class CsvEmitter(Emitter):

    def _get_label(self, field):
        if hasattr(self.handler, 'model'):
            model = self.handler.model
            try:
                return model._meta.get_field(field).verbose_name
            except FieldDoesNotExist:
                try:
                    return getattr(model(), field).short_description
                except (AttributeError, ObjectDoesNotExist):
                    for rel in model._meta.get_all_related_objects():
                        reverse_name = rel.get_accessor_name()
                        if field == reverse_name:
                            if isinstance(rel.field, models.OneToOneField):
                                return rel.model._meta.verbose_name
                            else:
                                return rel.model._meta.verbose_name_plural
        return field

    def cleaned_fields(self):
        cleaned_fields = []
        for field in self.fields:
            if not field.startswith('_'):
                cleaned_fields.append(field)
        return cleaned_fields

    def _render_dict_value(self, dict_value):
        value = dict_value.get('_obj_name')
        if value is None:

            value = '\t'.join([force_text(val) for key, val in dict_value.items() if not key.startswith('_')
                               and not isinstance(val, (dict, list))])
        return value or ''

    def _render_list_value(self, list_value):
        values = []
        for value in list_value:
            if isinstance(value, dict):
                value = self._render_dict_value(value)
            else:
                value = force_text(value)
            values.append(value)
        return '\n '.join(values)

    def render(self, request):
        output = io.StringIO()
        headers = []
        fields = self.cleaned_fields()

        for field in fields:
            headers.append(self._get_label(field))

        data = []
        for row in self.construct():
            out_row = []
            for field in fields:
                value = row.get(field)
                if isinstance(value, dict):
                    value = self._render_dict_value(value)
                elif isinstance(value, list):
                    value = self._render_list_value(value)

                if not value:
                    value = ''
                out_row.append(value)
            data.append(out_row)
        CsvGenerator().generate(headers, data, output)
        return output.getvalue()
