from pyston.paginator import BaseModelOffsetBasedPaginator


class ElasticsearchOffsetBasedPaginator(BaseModelOffsetBasedPaginator):

    def _get_total(self, qs, request):
        return qs.count()

    def _get_list_from_queryset(self, qs, from_, to_):
        return list(qs[from_:to_])

    def _get_model(self, qs):
        return qs._doc_type
