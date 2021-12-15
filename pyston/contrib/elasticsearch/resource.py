from pyston.resource import BaseModelResource
from pyston.serializer import ModelResourceSerializer, ModelSerializer, register
from pyston.utils.helpers import ModelIteratorHelper

from elasticsearch import NotFoundError
from elasticsearch_dsl import Document, Search

from .filters import ElasticsearchFilterManager
from .order import ElasticsearchOrderManager
from .paginator import ElasticsearchOffsetBasedPaginator


@register((Document, Search))
class ElasticsearchSerializer(ModelSerializer):

    obj_class = Document
    obj_iterable_classes = (ModelIteratorHelper, Search)

    def _field_to_python(self, field_name, real_field_name, obj, serialization_format, allow_tags=False, **kwargs):
        if field_name in obj._doc_type.mapping.properties:
            return self._data_to_python(
                self._value_to_raw_verbose(
                    getattr(obj, real_field_name),
                    obj,
                    allow_tags=False,
                    serialization_format=serialization_format,
                    **kwargs
                ),
                serialization_format,
                **kwargs
            )
        else:
            return super()._field_to_python(field_name, real_field_name, obj, serialization_format, allow_tags,
                                            **kwargs)


class ElasticsearchResourceSerializer(ModelResourceSerializer, ElasticsearchSerializer):

    obj_iterable_classes = (ModelIteratorHelper, Search)


class BaseElasticsearchResource(BaseModelResource):

    register = True
    abstract = True

    allowed_methods = ('get', 'head', 'options')
    serializer = ElasticsearchResourceSerializer
    paginator = ElasticsearchOffsetBasedPaginator()
    order_manager = ElasticsearchOrderManager()
    filter_manager = ElasticsearchFilterManager()

    def _get_queryset(self):
        return self.model.search()

    def _get_obj_or_none(self, pk=None):
        if not pk:
            return None
        try:
            return self.model.get(id=pk)
        except NotFoundError:
            return None
