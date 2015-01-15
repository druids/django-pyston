from __future__ import unicode_literals

import decimal
import json
import StringIO
import time

from django.db.models.fields import FieldDoesNotExist
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.encoding import smart_unicode, force_text
from django.utils.xmlutils import SimplerXMLGenerator
from django.core.serializers.json import DateTimeAwareJSONEncoder
from django.db.models.base import Model
from django.conf import settings
from django.utils.datastructures import SortedDict

from piston.file_generator import CsvGenerator, XlsxGenerator, PdfGenerator

from .datastructures import ModelSortedDict, Field, Fieldset


try:
    import cz_models
except ImportError:
    cz_models = None

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
        if name not in converters:
            converters[name] = (converter_class, content_type)
        return converter_class
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

    context_key = 'accept'
    if input:
        context_key = 'content_type'

    if mimeparse and context_key in request._rest_context:
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
                                                            request._rest_context[context_key])
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

    def encode(self, request, converted_data, resource, result):
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
        if isinstance(data, (list, tuple, set)):
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

    def encode(self, request, converted_data, resource, result):
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
    def encode(self, request, converted_data, resource, result):
        return json.dumps(
            converted_data, cls=DateTimeAwareJSONEncoder, ensure_ascii=False, indent=4
        )

    def decode(self, request, data):
        return json.loads(data)


class GeneratorConverter(Converter):
    """
    Generator converter is more complicated.
    Contains user readable informations (headers).
    Supports only output.
    Output is flat.

    It is necessary set generator_class as class attribute
    
    This class contains little bit low-level implementation
    """

    generator_class = None

    def _render_headers(self, field_name_list):
        result = []
        if len(field_name_list) == 1 and '' in field_name_list:
            return result

        for field_name in field_name_list:
            result.append(field_name)
        return result

    def _get_recursive_value_from_row(self, data, key_path):
        if len(key_path) == 0:
            return data

        if isinstance(data, dict):
            return self._get_recursive_value_from_row(data.get(key_path[0], ''), key_path[1:])
        elif isinstance(data, (list, tuple, set)):
            return [self._get_recursive_value_from_row(val, key_path) for val in data]
        else:
            return ''

    def render_value(self, value, first=True):
        if isinstance(value, dict):
            return '(%s)' % ', '.join(['%s: %s' % (key, self.render_value(val, False)) for key, val in value.items()])
        elif isinstance(value, (list, tuple, set)):
            if first:
                return '\n'.join([self.render_value(val, False) for val in value])
            else:
                return '(%s)' % ', '.join([self.render_value(val, False) for val in value])
        else:
            return force_text(value)

    def _get_value_from_row(self, data, field):
        return self.render_value(self._get_recursive_value_from_row(data, field.key_path) or '')

    def _render_content(self, field_name_list, converted_data):
        result = []

        constructed_data = converted_data
        if not isinstance(constructed_data, (list, tuple, set)):
            constructed_data = [constructed_data]

        for row in constructed_data:
            out_row = []
            for field in field_name_list:
                out_row.append(self._get_value_from_row(row, field))
            result.append(out_row)
        return result

    def encode(self, request, converted_data, resource, result):
        output = StringIO.StringIO()
        fieldset = Fieldset.create_from_data(converted_data)
        self.generator_class().generate(
            self._render_headers(fieldset),
            self._render_content(fieldset, converted_data),
            output
        )
        return output.getvalue()


@register('csv', 'text/csv; charset=utf-8')
class CsvConverter(GeneratorConverter):
    generator_class = CsvGenerator


if XlsxGenerator:
    @register('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    class XLSXConverter(GeneratorConverter):
        generator_class = XlsxGenerator


if PdfGenerator:
    @register('pdf', 'application/pdf; charset=utf-8')
    class PdfConverter(GeneratorConverter):
        generator_class = PdfGenerator
