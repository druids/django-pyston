from __future__ import unicode_literals

import json

from six.moves import cStringIO
from six import BytesIO

from django.utils.encoding import force_text
from django.utils.xmlutils import SimplerXMLGenerator
from django.core.serializers.json import DateTimeAwareJSONEncoder
from django.conf import settings

from pyston.file_generator import CSVGenerator, XLSXGenerator, PDFGenerator

from .datastructures import Field, FieldsetGenerator


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


def get_converter(result_format):
    """
    Gets an converter, returns the class and a content-type.
    """
    if result_format in converters:
        return converters.get(result_format)
    else:
        raise ValueError('No converter found for type {}'.format(result_format))


def get_converter_name_from_request(request, input_serialization=False):
    """
    Function for determining which converter name to use
    for output.
    """
    try:
        import mimeparse
    except ImportError:
        mimeparse = None

    default_converter_name = getattr(settings, 'PYSTON_DEFAULT_CONVERTER', 'json')

    context_key = 'accept'
    if input_serialization:
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
    return default_converter_name


def get_converter_from_request(request, input_serialization=False):
    """
    Function for determining which converter name to use
    for output.
    """

    return get_converter(get_converter_name_from_request(request, input_serialization))


def get_supported_mime_types():
    return [content_type for _, (_, content_type) in converters.items()]


class Converter(object):
    """
    Converter from standard data types to output format (JSON,YAML, Pickle) and from input to python objects
    """

    def encode(self, data, options, **kwargs):
        """
        Encode data to output
        """
        raise NotImplementedError

    def decode(self, data, **kwargs):
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
            for key, value in data.items():
                xml.startElement(key, {})
                self._to_xml(xml, value)
                xml.endElement(key)
        else:
            xml.characters(force_text(data))

    def encode(self, data, options, **kwargs):
        stream = cStringIO()

        xml = SimplerXMLGenerator(stream, 'utf-8')
        xml.startDocument()
        xml.startElement('response', {})

        self._to_xml(xml, data)

        xml.endElement('response')
        xml.endDocument()

        return stream.getvalue()


@register('json', 'application/json; charset=utf-8')
class JSONConverter(Converter):

    """
    JSON emitter, understands timestamps.
    """
    def encode(self, data, options, **kwargs):
        return json.dumps(data, cls=DateTimeAwareJSONEncoder, ensure_ascii=False, **options)

    def decode(self, data, **kwargs):
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

    def _get_output(self):
        return BytesIO()

    def encode(self, data, options, resource=None, fields_string=None, **kwargs):
        output = self._get_output()
        fieldset = FieldsetGenerator(data, resource, fields_string).generate()
        self.generator_class().generate(
            self._render_headers(fieldset),
            self._render_content(fieldset, data),
            output
        )
        return output.getvalue()


@register('csv', 'text/csv; charset=utf-8')
class CSVConverter(GeneratorConverter):
    generator_class = CSVGenerator

    def _get_output(self):
        return cStringIO()


if XLSXGenerator:
    @register('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    class XLSXConverter(GeneratorConverter):
        generator_class = XLSXGenerator


if PDFGenerator:
    @register('pdf', 'application/pdf; charset=utf-8')
    class PDFConverter(GeneratorConverter):
        generator_class = PDFGenerator
