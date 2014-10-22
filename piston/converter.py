from __future__ import unicode_literals

import json
import StringIO

from django.db.models.fields import FieldDoesNotExist
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.encoding import smart_unicode, force_text
from django.utils.xmlutils import SimplerXMLGenerator
from django.core.serializers.json import DateTimeAwareJSONEncoder
from django.db.models.base import Model
from django.conf import settings

from .csv_generator import CsvGenerator


try:
    # yaml isn't standard with python.  It shouldn't be required if it
    # isn't used.
    import yaml
except ImportError:
    yaml = None

try:
    import cPickle as pickle
except ImportError:
    import pickle


converters = {}


def register(name, content_type):
    """
    Register an converter.

    Parameters::
     - `name`: The name of the converter ('json', 'xml', 'yaml', ...)
     - `converter_class`: The converter class.
     - `content_type`: The content type to serve response as.
    """

    def _register(converter_class):
        converters[name] = (converter_class, content_type)
    return _register


def get_converter(format):
    """
    Gets an converter, returns the class and a content-type.
    """
    if converters.has_key(format):
        return converters.get(format)

    raise ValueError('No converter found for type %s' % format)


def get_converter_from_request(request, input=False):
    """
    Function for determening which converter to use
    for output. It lives here so you can easily subclass
    `Resource` in order to change how emission is detected.
    """
    try:
        import mimeparse
    except ImportError:
        mimeparse = None

    default_converter_name = getattr(settings, 'PISTON_DEFAULT_CONVERTER', 'json')

    header_name = 'HTTP_ACCEPT'
    if input:
        header_name = 'CONTENT_TYPE'

    if mimeparse and header_name in request.META:
        supported_mime_types = set()
        converter_map = {}
        preferred_content_type = None
        for name, (_, content_type) in converters.items():
            content_type_without_encoding = content_type.split(';')[0]
            if default_converter_name and name == default_converter_name:
                preferred_content_type = content_type_without_encoding
            supported_mime_types.add(content_type_without_encoding)
            converter_map[content_type_without_encoding] = name
        supported_mime_types = list(supported_mime_types)
        if preferred_content_type:
            supported_mime_types.append(preferred_content_type)
        try:
            preferred_content_type = mimeparse.best_match(supported_mime_types,
                                                            request.META[header_name])
        except ValueError:
            pass
        default_converter_name = converter_map.get(preferred_content_type, default_converter_name)
    return get_converter(default_converter_name)


def get_supported_mime_types():
    return [content_type for _, (_, content_type) in converters.items()]


class Converter(object):
    """
    Converter from standard data types to output format (JSON,YAML, Pickle) and from input to python objects
    """

    def encode(self, request, converted_data, resource, result, field_name_list):
        """
        Encode data to output
        """
        raise NotImplementedError

    def decode(self, request, data):
        """
        Decode data to input
        """
        raise NotImplementedError


@register('xml', 'text/xml; charset=utf-8')
class XMLConverter(Converter):
    """
    Converter for XML.
    Supports only output conversion
    """

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

    def encode(self, request, converted_data, resource, result, field_name_list):
        stream = StringIO.StringIO()

        xml = SimplerXMLGenerator(stream, "utf-8")
        xml.startDocument()
        xml.startElement("response", {})

        self._to_xml(xml, converted_data)

        xml.endElement("response")
        xml.endDocument()

        return stream.getvalue()


@register('json', 'application/json; charset=utf-8')
class JSONConverter(Converter):
    """
    JSON emitter, understands timestamps.
    """
    def encode(self, request, converted_data, resource, result, field_name_list):
        return json.dumps(
            converted_data, cls=DateTimeAwareJSONEncoder, ensure_ascii=False, indent=4
        )

    def decode(self, request, data):
        return json.loads(data)


if yaml:
    @register('yaml', 'application/x-yaml; charset=utf-8')
    class YAMLConverter(Converter):
        """
        YAML emitter, uses `safe_dump` to omit the
        specific types when outputting to non-Python.
        """
        def encode(self, request, converted_data, resource, result, field_name_list):
            return yaml.safe_dump(converted_data)

        def decode(self, request, data):
            return dict(yaml.safe_load(data))


@register('pickle', 'application/python-pickle')
class PickleConverter(Converter):
    """
    Emitter that returns Python pickled. 
    Support only output conversion
    """
    def encode(self, request, converted_data, resource, result, field_name_list):
        return pickle.dumps(converted_data)


# TODO: FIX
@register('csv', 'text/csv; charset=utf-8')
class CsvConverter(Converter):
    """
    CSV converter is more complicated.
    Contains user readable informations (headers).
    Supports only output.
    Output is flat.
    """

    def _get_field_label_from_model_related_objects(self, resource, field_name):
        for rel in resource.model._meta.get_all_related_objects():
            reverse_name = rel.get_accessor_name()
            if field_name == reverse_name:
                if isinstance(rel.field, models.OneToOneField):
                    return rel.model._meta.verbose_name
                else:
                    return rel.model._meta.verbose_name_plural
        return None

    def _get_field_label_from_model_method(self, resource, field_name):
        return getattr(resource.model(), field_name).short_description

    def _get_field_label_from_model_field(self, resource, field_name):
        return resource.model._meta.get_field(field_name).verbose_name

    def _get_field_label_from_model(self, resource, field_name):
        try:
            return self._get_field_label_from_model_field(resource, field_name)
        except FieldDoesNotExist:
            try:
                return self._get_label_from_model_method(resource, field_name)
            except (AttributeError, ObjectDoesNotExist):
                return self._get_field_label_from_model_related_objects(resource, field_name)
        return None

    def _get_field_label(self, resource, field_name):
        result = None
        if hasattr(resource, 'model') and isinstance(resource.model, Model):
            result = self._get_field_label_from_model(resource, field_name)
        return result or field_name

    def _select_fields(self, field_name_list):
        result = []
        for field_name in field_name_list:
            if isinstance(field_name, (tuple, list)):
                field_name = field_name[0]
            if not field_name.startswith('_'):
                result.append(field_name)
        return result

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

    def _render_headers(self, resource, field_name_list):
        result = []
        for field_name in field_name_list:
            result.append(self._get_field_label(resource, field_name))
        return result

    def _get_value_from_row(self, row, field_name):
        value = row.get(field_name)
        if isinstance(value, dict):
            value = self._render_dict_value(value)
        elif isinstance(value, list):
            value = self._render_list_value(value)
        return value or ''

    def _render_content(self, resource, field_name_list, converted_data):
        result = []

        constructed_data = converted_data
        if not isinstance(constructed_data, (list, tuple)):
            constructed_data = [constructed_data]

        for row in constructed_data:
            out_row = []
            for field_name in field_name_list:
                out_row.append(self._get_value_from_row(row, field_name))
            result.append(out_row)
        return result

    def encode(self, request, converted_data, resource, result, field_name_list):
        output = StringIO.StringIO()
        selected_field_name_list = self._select_fields(field_name_list)
        if isinstance(converted_data, (dict, list, tuple)):
            CsvGenerator().generate(
                self._render_headers(resource, selected_field_name_list),
                self._render_content(resource, selected_field_name_list, converted_data),
                output
            )
        return output.getvalue()
