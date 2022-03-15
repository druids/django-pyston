from pyston.order.sorters import BaseSorter
from pyston.order.managers import BaseParserModelOrderManager
from pyston.order.utils import DirectionSlug


class DynamoSorter(BaseSorter):

    def get_order_term(self):
        return self.direction == DirectionSlug.ASC


class DynamoOrderManager(BaseParserModelOrderManager):

    def _sort_queryset(self, qs, terms):
        for term in terms:
            qs = qs.set_scan_index_forward(term)
        return qs

    def _get_sorter_from_model(self, identifiers_prefix, identifiers, direction, model, resource, request,
                               order_fields_rfs):
        if len(identifiers) == 1:
            current_identifier = self._get_real_field_name(resource, identifiers[0])
            if current_identifier == resource.get_range_key():
                return DynamoSorter(identifiers_prefix + identifiers, direction)
        return None
