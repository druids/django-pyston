from pyston.resource import BaseModelResource
from pyston.serializer import ModelResourceSerializer, ModelSerializer, Serializer, register

from pydjamodb.queryset import DynamoDBQuerySet
from pynamodb.attributes import MapAttribute
from pynamodb.models import Model
from pynamodb.pagination import ResultIterator

from .order import DynamoOrderManager
from .filter import DynamoFilterManager
from .paginator import DynamoCursorBasedPaginator


@register(MapAttribute)
class MapAttributeSerializer(Serializer):

    def serialize(self, data, serialization_format, **kwargs):
        return {
            k: self._data_to_python(v, serialization_format, **kwargs)
            for k, v in data.attribute_values.items()
        }


@register((Model, ResultIterator))
class DynamoSerializer(ModelSerializer):

    obj_class = Model
    obj_iterable_classes = (ResultIterator, DynamoDBQuerySet)


class DynamoResourceSerializer(ModelResourceSerializer, DynamoSerializer):

    obj_iterable_classes = (ResultIterator, DynamoDBQuerySet)


class BaseDynamoResource(BaseModelResource):

    register = True
    abstract = True

    allowed_methods = ('get', 'head', 'options')
    paginator = DynamoCursorBasedPaginator()
    serializer = DynamoResourceSerializer
    order_manager = DynamoOrderManager()
    filter_manager = DynamoFilterManager()

    range_key = None

    def _get_hash_key(self):
        raise NotImplementedError

    def _get_obj_or_none(self, pk=None):
        if not pk:
            return None
        try:
            return self.model.get(self._get_hash_key(), pk)
        except self.model.DoesNotExist:
            return None

    def _get_queryset(self):
        return self.model.objects.set_hash_key(self._get_hash_key())

    def get_range_key(self):
        return self.range_key
