import json
from django.db.models.fields import FieldDoesNotExist
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.encoding import smart_unicode, force_text
from piston.utils import CsvGenerator
from django.utils.xmlutils import SimplerXMLGenerator

try:
    # yaml isn't standard with python.  It shouldn't be required if it
    # isn't used.
    import yaml
except ImportError:
    yaml = None

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

try:
    import cPickle as pickle
except ImportError:
    import pickle

from django.core.serializers.json import DateTimeAwareJSONEncoder


class Converter(object):

    CONVERTERS = {}

    def encode(self, request, converted_dict, resource, result):
        raise NotImplementedError

    def decode(self, request, data):
        raise NotImplementedError

    @classmethod
    def get(cls, format):
        """
        Gets an converter, returns the class and a content-type.
        """
        if cls.CONVERTERS.has_key(format):
            return cls.CONVERTERS.get(format)

        raise ValueError('No converter found for type %s' % format)

    @classmethod
    def register(cls, name, klass, content_type='text/plain'):
        """
        Register an converter.

        Parameters::
         - `name`: The name of the converter ('json', 'xml', 'yaml', ...)
         - `klass`: The converter class.
         - `content_type`: The content type to serve response as.
        """
        cls.CONVERTERS[name] = (klass, content_type)

    @classmethod
    def unregister(cls, name):
        """
        Remove an converter from the registry. Useful if you don't
        want to provide output in one of the built-in converters.
        """
        return cls.CONVERTERS.pop(name, None)


class XMLConverter(Converter):

    def _to_xml(self, xml, data):
        if isinstance(data, (list, tuple)):
            for item in data:
                xml.startElement('resource', {})
                self._to_xml(xml, item)
                xml.endElement('resource')
        elif isinstance(data, dict):
            for key, value in data.iteritems():
                xml.startElement(key, {})
                self._to_xml(xml, value)
                xml.endElement(key)
        else:
            xml.characters(smart_unicode(data))

    def encode(self, request, converted_dict, resource, result):
        stream = StringIO.StringIO()

        xml = SimplerXMLGenerator(stream, "utf-8")
        xml.startDocument()
        xml.startElement("response", {})

        self._to_xml(xml, self.result)

        xml.endElement("response")
        xml.endDocument()

        return stream.getvalue()


class JSONConverter(Converter):
    """
    JSON emitter, understands timestamps.
    """
    def encode(self, request, converted_dict, resource, result):
        return json.dumps(converted_dict,
                           cls=DateTimeAwareJSONEncoder,
                           ensure_ascii=False, indent=4)

    def decode(self, request, data):
        return json.loads(data)



class YAMLEmitter(Converter):
    """
    YAML emitter, uses `safe_dump` to omit the
    specific types when outputting to non-Python.
    """
    def encode(self, request, converted_dict, resource, result):
        return yaml.safe_dump(converted_dict)

    def decode(self, request, data):
        return dict(yaml.safe_load(data))


class PickleEmitter(Converter):
    """
    Emitter that returns Python pickled.
    """
    def encode(self, request, converted_dict, resource, result):
        return pickle.dumps(converted_dict)


class CsvEmitter(Converter):

    def _get_label(self, resource, field):
        if hasattr(resource, 'model'):
            model = resource.model
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

    def cleaned_fields(self, fields):
        cleaned_fields = []
        for field in fields:
            if isinstance(field, (tuple, list)):
                field = field[0]

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

    # TODO fix
    def encode(self, request, converted_dict, resource, result):
        output = StringIO()
        headers = []
        fields = self.cleaned_fields()

        for field in fields:
            headers.append(self._get_label(field))

        data = []
        constructed_data = self.converted_dict
        if not isinstance(constructed_data, (list, tuple)):
            constructed_data = [constructed_data]

        for row in constructed_data:
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


Converter.register('xml', XMLConverter, 'text/xml; charset=utf-8')
Converter.register('json', JSONConverter, 'application/json; charset=utf-8')
if yaml:  # Only register yaml if it was import successfully.
    Converter.register('yaml', YAMLEmitter, 'application/x-yaml; charset=utf-8')
Converter.register('pickle', PickleEmitter, 'application/python-pickle')
