import re

from pyston.converters import JSONConverter, is_collection


def to_camel_case(snake_str):
    if snake_str.startswith('_'):
        return '_' + to_camel_case(snake_str[1:])
    else:
        components = snake_str.split('_')
        # We capitalize the first letter of each component except the first one
        # with the 'title' method and join them together.
        return components[0] + ''.join(x.title() for x in components[1:])


def to_snake_case(name):
    s1 = re.sub('(.)([A-Z])', r'\1_\2', name)
    return re.sub('([^_])([A-Z])', r'\1_\2', s1).lower()


class JSONCamelCaseConverter(JSONConverter):

    def _encode_snake_to_camel(self, data):
        from pyston.serializer import LAZY_SERIALIZERS

        if isinstance(data, LAZY_SERIALIZERS):
            return self._encode_snake_to_camel(data.serialize())
        elif is_collection(data):
            return (self._encode_snake_to_camel(item) for item in data)
        elif isinstance(data, dict):
            return {to_camel_case(key): self._encode_snake_to_camel(val) for key, val in data.items()}
        else:
            return data

    def _decode_camel_to_snake(self, data):
        if is_collection(data):
            return [self._decode_camel_to_snake(item) for item in data]
        elif isinstance(data, dict):
            return {to_snake_case(key): self._decode_camel_to_snake(val) for key, val in data.items()}
        else:
            return data

    def _encode_to_stream(self, output_stream, data, options=None, **kwargs):
        super()._encode_to_stream(output_stream, self._encode_snake_to_camel(data), options=None, **kwargs)

    def _decode(self, data, **kwargs):
        return self._decode_camel_to_snake(super(JSONCamelCaseConverter, self)._decode(data))
