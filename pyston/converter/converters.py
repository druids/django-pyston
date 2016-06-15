from django.core.serializers.json import DateTimeAwareJSONEncoder



@register('json', 'application/json; charset=utf-8')
class JSONConverter(Converter):

    """
    JSON emitter, understands timestamps.
    """
    def encode(self, serializer, **kwargs):
        return json.dumps(data, cls=DateTimeAwareJSONEncoder, ensure_ascii=False, indent=4)

    def decode(self, data, **kwargs):
        return json.loads(data)
