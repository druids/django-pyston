from pyston.utils import LOOKUP_SEP
from pyston.filters.filters import Filter
from pyston.filters.utils import OperatorSlug
from pyston.filters.exceptions import OperatorFilterError
from pyston.filters.managers import BaseParserModelFilterManager


class BaseDynamoFilter(Filter):

    allowed_operators = None

    def get_allowed_operators(self):
        return self.allowed_operators

    def clean_value(self, value, operator_slug, request):
        return value

    def get_q(self, value, operator_slug, request):
        if operator_slug not in self.get_allowed_operators():
            raise OperatorFilterError
        else:
            return self.get_filter_term(self.clean_value(value, operator_slug, request), operator_slug, request)

    def get_filter_term(self, value, operator_slug, request):
        raise NotImplementedError


class DynamoFilterManager(BaseParserModelFilterManager):

    def _logical_conditions_and(self, condition_a, condition_b):
        conditions_union = {**condition_a, **condition_b}
        sorted_keys = sorted(conditions_union)
        if len(condition_a) == 1 and len(condition_b) == 1 and len(sorted_keys) == 2:
            condition_a_full_identifier, condition_b_full_identifier = sorted_keys
            condition_a_identifier, condition_a_operator = condition_a_full_identifier.rsplit(LOOKUP_SEP, 1)
            condition_b_identifier, condition_b_operator = condition_b_full_identifier.rsplit(LOOKUP_SEP, 1)
            if (condition_a_identifier == condition_b_identifier and condition_a_operator == OperatorSlug.GTE
                    and condition_b_operator == OperatorSlug.LT):
                return {
                    f'{condition_a_identifier}__between': (
                        conditions_union[condition_a_full_identifier], conditions_union[condition_b_full_identifier]
                    )
                }
        return super()._logical_conditions_and(condition_a, condition_b)

    def _filter_queryset(self, qs, q):
        return qs.filter(**q)
