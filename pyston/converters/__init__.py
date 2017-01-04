from __future__ import unicode_literals

import types
import json

from six.moves import cStringIO

from django.conf import settings
from django.core.serializers.json import DateTimeAwareJSONEncoder
from django.utils.encoding import force_text
from django.utils.xmlutils import SimplerXMLGenerator
from django.template.loader import get_template

from pyston.utils.helpers import UniversalBytesIO
from pyston.utils.datastructures import FieldsetGenerator

from .file_generators import CSVGenerator, XLSXGenerator, PDFGenerator

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

    def _encode(self, data, options, **kwargs):
        """
        Encodes data to output string. You must implement this method or change implementation encode_to_stream method.
        """
        raise NotImplementedError

    def _decode(self, data, **kwargs):
        """
        Decodes data to string input
        """
        raise NotImplementedError

    def _encode_to_stream(self, os, data, options, **kwargs):
        """
        Encodes data and writes it to the output stream
        """
        self._get_output_stream(os).write(self._encode(data, options, **kwargs))

    def encode_to_stream(self, os, data, options, **kwargs):
        self._encode_to_stream(self._get_output_stream(os), data, options, **kwargs)

    def decode(self, data, **kwargs):
        return self._decode(data, **kwargs)

    def _get_output_stream(self, os):
        return os if isinstance(os, UniversalBytesIO) else UniversalBytesIO(os)


@register('xml', 'text/xml; charset=utf-8')
class XMLConverter(Converter):
    """
    Converter for XML.
    Supports only output conversion
    """

    def _to_xml(self, xml, data):
        from pyston.serializer import LazySerializedData

        if isinstance(data, LazySerializedData):
            self._to_xml(xml, data.serialize())
        elif isinstance(data, (list, tuple, set, types.GeneratorType)):
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

    def _encode(self, data, options, **kwargs):
        if data:
            stream = cStringIO()

            xml = SimplerXMLGenerator(stream, 'utf-8')
            xml.startDocument()
            xml.startElement('response', {})

            self._to_xml(xml, data)

            xml.endElement('response')
            xml.endDocument()

            return stream.getvalue()
        else:
            return ''


class LazyDateTimeAwareJSONEncoder(DateTimeAwareJSONEncoder):

    def default(self, o):
        from pyston.serializer import LazySerializedData

        if isinstance(o, types.GeneratorType):
            return tuple(o)
        elif isinstance(o, LazySerializedData):
            return o.serialize()
        else:
            return super(LazyDateTimeAwareJSONEncoder, self).default(o)


@register('json', 'application/json; charset=utf-8')
class JSONConverter(Converter):
    """
    JSON emitter, understands timestamps.
    """

    def _encode_to_stream(self, os, data, options, **kwargs):
        if data:
            json.dump(data, os, cls=LazyDateTimeAwareJSONEncoder, ensure_ascii=False, **options)

    def _decode(self, data, **kwargs):
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
        from pyston.serializer import LazySerializedData

        if isinstance(data, LazySerializedData):
            return self._get_recursive_value_from_row(data.serialize(), key_path)
        elif len(key_path) == 0:
            return data
        elif isinstance(data, dict):
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

    def _render_row(self, row, field_name_list):
        return (self._get_value_from_row(row, field) for field in field_name_list)

    def _render_content(self, field_name_list, converted_data):
        constructed_data = converted_data
        if not isinstance(constructed_data, (list, tuple, set, types.GeneratorType)):
            constructed_data = [constructed_data]

        return (self._render_row(row, field_name_list) for row in constructed_data)

    def _encode_to_stream(self, os, data, options, resource=None, fields_string=None, **kwargs):
        fieldset = FieldsetGenerator(resource, fields_string).generate()
        self.generator_class().generate(
            self._render_headers(fieldset),
            self._render_content(fieldset, data),
            os
        )


@register('csv', 'text/csv; charset=utf-8')
class CSVConverter(GeneratorConverter):
    generator_class = CSVGenerator


if XLSXGenerator:
    @register('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    class XLSXConverter(GeneratorConverter):
        generator_class = XLSXGenerator


if PDFGenerator:
    @register('pdf', 'application/pdf; charset=utf-8')
    class PDFConverter(GeneratorConverter):
        generator_class = PDFGenerator


@register('html', 'text/html; charset=utf-8')
class HTMLConverter(Converter):
    """
    Converter for HTML.
    Supports only output conversion
    """

    def _encode(self, data, options, http_headers=None, resource=None, result=None, **kwargs):
        from pyston.resource import BaseObjectResource

        http_headers = {} if http_headers is None else http_headers.copy()
        http_headers['Content-Type'] = 'application/json; charset=utf-8'

        kwargs.update({
            'http_headers': http_headers,
            'resource': resource,
        })

        is_single_obj_resource = resource._is_single_obj_request(result)
        inst = result if is_single_obj_resource else None

        if isinstance(resource, BaseObjectResource):
            form = resource._get_form(inst=inst)
            form.method = 'put' if is_single_obj_resource else 'post'
            kwargs['form'] = form

        data_stream = UniversalBytesIO()
        JSONConverter()._encode_to_stream(data_stream, data, {'indent': 4}, **kwargs)

        kwargs['output'] = data_stream.get_string_value()

        return get_template('pyston/base.html').render(kwargs)
