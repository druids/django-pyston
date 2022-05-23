from pyston.order.exceptions import OrderIdentifierError
from pyston.order.managers import BaseParserModelOrderManager
from pyston.order.sorters import BaseSorter
from pyston.order.utils import DirectionSlug
from pyston.utils import LOOKUP_SEP


class ElasticsearchSorter(BaseSorter):

    def get_order_term(self):
        term = LOOKUP_SEP.join(self.identifiers)
        return f'-{term}' if self.direction == DirectionSlug.DESC else term


class ElasticsearchOrderManager(BaseParserModelOrderManager):

    order_by_field_name = {'boolean', 'date', 'keyword', 'float', 'integer'}

    def _sort_queryset(self, qs, terms):
        return qs.sort(*terms)

    def _get_sorter_from_model(self, identifiers_prefix, identifiers, direction, model, resource, request,
                               order_fields_rfs):
        if len(identifiers) == 1:
            current_identifier = self._get_real_field_name(resource, identifiers[0])

            if current_identifier not in order_fields_rfs:
                raise OrderIdentifierError

            try:
                field = model._doc_type.mapping.properties[current_identifier]
                field_name = field.name
                if hasattr(field, 'builtin_type') and field_name not in self.order_by_field_name:
                    field_name = field.builtin_type.name
                if field_name in self.order_by_field_name:
                    return ElasticsearchSorter(identifiers_prefix + identifiers, direction)
            except KeyError:
                pass
        return None
