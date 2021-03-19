import types
import json

from io import StringIO

from collections import OrderedDict

from defusedxml import ElementTree as ET
from django.core.serializers.json import DjangoJSONEncoder
from django.http.response import HttpResponseBase
from django.template.loader import get_template
from django.utils.encoding import force_text
from django.utils.xmlutils import SimplerXMLGenerator
from django.utils.module_loading import import_string
from django.utils.html import format_html

from pyston.utils.helpers import UniversalBytesIO, serialized_data_to_python
from pyston.utils.datastructures import FieldsetGenerator
from pyston.conf import settings

from .file_generators import CSVGenerator, XLSXGenerator, PDFGenerator, TXTGenerator


def is_collection(data):
    return isinstance(data, (list, tuple, set, types.GeneratorType))


def get_default_converters():
    """
    Register all converters from settings configuration.
    """
    converters = OrderedDict()
    for converter_class_path in settings.CONVERTERS:
        converter_class = import_string(converter_class_path)()
        converters[converter_class.format] = converter_class
    return converters


def get_default_converter_name(converters=None):
    """
    Gets default converter name
    """
    converters = get_default_converters() if converters is None else converters
    return list(converters.keys())[0]


def get_converter(result_format, converters=None):
    """
    Gets an converter, returns the class and a content-type.
    """
    converters = get_default_converters() if converters is None else converters

    if result_format in converters:
        return converters.get(result_format)
    else:
        raise ValueError('No converter found for type {}'.format(result_format))


def get_converter_name_from_request(request, converters=None, input_serialization=False):
    """
    Function for determining which converter name to use
    for output.
    """
    try:
        import mimeparse
    except ImportError:
        mimeparse = None

    context_key = 'accept'
    if input_serialization:
        context_key = 'content_type'

    converters = get_default_converters() if converters is None else converters

    default_converter_name = get_default_converter_name(converters)

    if mimeparse and context_key in request._rest_context:
        supported_mime_types = set()
        converter_map = {}
        preferred_content_type = None
        for name, converter_class in converters.items():
            if name == default_converter_name:
                preferred_content_type = converter_class.media_type
            supported_mime_types.add(converter_class.media_type)
            converter_map[converter_class.media_type] = name
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


def get_converter_from_request(request, converters=None, input_serialization=False):
    """
    Function for determining which converter name to use
    for output.
    """

    return get_converter(get_converter_name_from_request(request, converters, input_serialization), converters)


def get_supported_mime_types(converters):
    return [converter.media_type for _, converter in converters.items()]


class Converter:
    """
    Converter from standard data types to output format (JSON,YAML, Pickle) and from input to python objects
    """
    charset = 'utf-8'
    media_type = None
    format = None
    allow_tags = False

    @property
    def content_type(self):
        return '{}; charset={}'.format(self.media_type, self.charset)

    def _encode(self, data, options=None, **kwargs):
        """
        Encodes data to output string. You must implement this method or change implementation encode_to_stream method.
        """
        raise NotImplementedError

    def _decode(self, data, **kwargs):
        """
        Decodes data to string input
        """
        raise NotImplementedError

    def _encode_to_stream(self, output_stream, data, options=None, **kwargs):
        """
        Encodes data and writes it to the output stream
        """
        output_stream.write(self._encode(data, options=options, **kwargs))

    def encode_to_stream(self, output_stream, data, options=None, **kwargs):
        self._encode_to_stream(self._get_output_stream(output_stream), data, options=options, **kwargs)

    def decode(self, data, **kwargs):
        return self._decode(data, **kwargs)

    def _get_output_stream(self, output_stream):
        return output_stream if isinstance(output_stream, UniversalBytesIO) else UniversalBytesIO(output_stream)


class XMLConverter(Converter):
    """
    Converter for XML.
    Supports only output conversion
    """
    media_type = 'text/xml'
    format = 'xml'
    root_element_name = 'response'

    def _to_xml(self, xml, data):
        from pyston.serializer import LAZY_SERIALIZERS

        if isinstance(data, LAZY_SERIALIZERS):
            self._to_xml(xml, data.serialize())
        elif is_collection(data):
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

    def _encode(self, data, **kwargs):
        if data is not None:
            stream = StringIO()

            xml = SimplerXMLGenerator(stream, 'utf-8')
            xml.startDocument()
            xml.startElement(self.root_element_name, {})

            self._to_xml(xml, data)

            xml.endElement(self.root_element_name)
            xml.endDocument()

            return stream.getvalue()
        else:
            return ''

    def _decode(self, data, **kwargs):
        return ET.fromstring(data)


class LazyDjangoJSONEncoder(DjangoJSONEncoder):

    def default(self, o):
        from pyston.serializer import LAZY_SERIALIZERS

        if isinstance(o, types.GeneratorType):
            return tuple(o)
        elif isinstance(o, LAZY_SERIALIZERS):
            return o.serialize()
        else:
            return super(LazyDjangoJSONEncoder, self).default(o)


class JSONConverter(Converter):
    """
    JSON emitter, understands timestamps.
    """
    media_type = 'application/json'
    format = 'json'

    def _encode_to_stream(self, output_stream, data, options=None, **kwargs):
        options = settings.JSON_CONVERTER_OPTIONS if options is None else options
        if data is not None:
            json.dump(data, output_stream, cls=LazyDjangoJSONEncoder, ensure_ascii=False, **options)

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
        from pyston.serializer import LAZY_SERIALIZERS

        if isinstance(data, LAZY_SERIALIZERS):
            return self._get_recursive_value_from_row(data.serialize(), key_path)
        elif len(key_path) == 0:
            return data
        elif isinstance(data, dict):
            return self._get_recursive_value_from_row(data.get(key_path[0], ''), key_path[1:])
        elif is_collection(data):
            return [self._get_recursive_value_from_row(val, key_path) for val in data]
        else:
            return ''

    def _render_dict(self, value, first):
        if first:
            return '\n'.join(('{}: {}'.format(key, self.render_value(val, False)) for key, val in value.items()))
        else:
            return '({})'.format(
                ', '.join(('{}: {}'.format(key, self.render_value(val, False)) for key, val in value.items()))
            )

    def _render_iterable(self, value, first):
        if first:
            return '\n'.join((self.render_value(val, False) for val in value))
        else:
            return '({})'.format(', '.join((self.render_value(val, False) for val in value)))

    def render_value(self, value, first=True):
        if isinstance(value, dict):
            return self._render_dict(value, first)
        elif is_collection(value):
            return self._render_iterable(value, first)
        else:
            return force_text(value)

    def _get_value_from_row(self, data, field):
        return self.render_value(self._get_recursive_value_from_row(data, field.key_path) or '')

    def _render_row(self, row, field_name_list):
        return (self._get_value_from_row(row, field) for field in field_name_list)

    def _render_content(self, field_name_list, converted_data):
        constructed_data = converted_data
        if not is_collection(constructed_data):
            constructed_data = [constructed_data]

        return (self._render_row(row, field_name_list) for row in constructed_data)

    def _encode_to_stream(self, output_stream, data, resource=None, requested_fields=None, direct_serialization=False,
                          **kwargs):
        fieldset = FieldsetGenerator(
            resource,
            force_text(requested_fields) if requested_fields is not None else None,
            direct_serialization=direct_serialization
        ).generate()
        self.generator_class().generate(
            self._render_headers(fieldset),
            self._render_content(fieldset, data),
            output_stream
        )


class CSVConverter(GeneratorConverter):
    """
    Converter for CSV response.
    Supports only output conversion
    """

    generator_class = CSVGenerator
    media_type = 'text/csv'
    format = 'csv'
    allow_tags = True


class XLSXConverter(GeneratorConverter):
    """
    Converter for XLSX response.
    For its use must be installed library xlsxwriter
    Supports only output conversion
    """

    generator_class = XLSXGenerator
    media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    format = 'xlsx'
    allow_tags = True


class PDFConverter(GeneratorConverter):
    """
    Converter for PDF response.
    For its use must be installed library pisa
    Supports only output conversion
    """

    generator_class = PDFGenerator
    media_type = 'application/pdf'
    format = 'pdf'


class TXTConverter(GeneratorConverter):
    """
    Converter for TXT response.
    Supports only output conversion
    """

    generator_class = TXTGenerator
    media_type = 'plain/text'
    format = 'txt'
    allow_tags = True


class HTMLConverter(Converter):
    """
    Converter for HTML.
    Supports only output conversion and should be used only for debug
    """

    media_type = 'text/html'
    format = 'html'
    template_name = 'pyston/html_converter.html'

    def _get_put_form(self, resource, obj):
        from pyston.resource import BaseObjectResource

        return (
            resource._get_form(inst=obj)
            if isinstance(resource, BaseObjectResource) and resource.has_put_permission(obj=obj)
            else None
        )

    def _get_post_form(self, resource, obj):
        from pyston.resource import BaseObjectResource

        return (
            resource._get_form(inst=obj)
            if isinstance(resource, BaseObjectResource) and resource.has_post_permission(obj=obj)
            else None
        )

    def _get_forms(self, resource, obj):
        return {
            'post': self._get_post_form(resource, obj),
            'put': self._get_put_form(resource, obj),
        }

    def _get_converter(self, resource):
        return JSONConverter()

    def _get_permissions(self, resource, obj):
        return {
            'post': resource.has_post_permission(obj=obj),
            'get': resource.has_get_permission(obj=obj),
            'put': resource.has_put_permission(obj=obj),
            'delete': resource.has_delete_permission(obj=obj),
            'head': resource.has_head_permission(obj=obj),
            'options': resource.has_options_permission(obj=obj),
        } if resource else {}

    def _update_headers(self, http_headers, resource, converter):
        http_headers['Content-Type'] = converter.content_type
        return http_headers

    def encode_to_stream(self, output_stream, data, options=None, **kwargs):
        assert output_stream is not HttpResponseBase, 'Output stream must be http response'

        self._get_output_stream(output_stream).write(
            self._encode(data, response=output_stream, options=options, **kwargs)
        )

    def _convert_url_to_links(self, data):
        if isinstance(data, list):
            return [self._convert_url_to_links(val) for val in data]
        elif isinstance(data, dict):
            return OrderedDict((
                (key, format_html('<a href=\'{0}\'>{0}</a>', val) if key == 'url' else self._convert_url_to_links(val))
                for key, val in data.items()
            ))
        else:
            return data

    def _encode(self, data, response=None, http_headers=None, resource=None, result=None, **kwargs):
        from pyston.resource import BaseObjectResource

        http_headers = {} if http_headers is None else http_headers.copy()
        converter = self._get_converter(resource)

        http_headers = self._update_headers(http_headers, resource, converter)
        obj = (
            resource._get_obj_or_none() if isinstance(resource, BaseObjectResource) and resource.has_permission()
            else None
        )

        kwargs.update({
            'http_headers': http_headers,
            'resource': resource,
        })

        data_stream = UniversalBytesIO()
        converter._encode_to_stream(data_stream, self._convert_url_to_links(serialized_data_to_python(data)), **kwargs)

        context = kwargs.copy()
        context.update({
            'permissions': self._get_permissions(resource, obj),
            'forms': self._get_forms(resource, obj),
            'output': data_stream.getvalue(),
            'name': resource._get_name() if resource and resource.has_permission() else response.status_code
        })

        # All responses has set 200 response code, because response can return status code without content (204) and
        # browser doesn't render it
        response.status_code = 200

        return get_template(self.template_name).render(context, request=resource.request if resource else None)
