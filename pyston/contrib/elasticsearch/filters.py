from pyston.filters.filters import Filter, BooleanFilterMixin, DateFilterMixin
from pyston.filters.utils import OperatorSlug
from pyston.filters.exceptions import OperatorFilterError
from pyston.filters.managers import BaseParserModelFilterManager

from elasticsearch_dsl import Q


class ElasticsearchFilter(Filter):

    allowed_operators = None

    def get_q(self, value, operator_slug, request):
        if operator_slug not in self.get_allowed_operators():
            raise OperatorFilterError
        else:
            return self.get_filter_term(self.clean_value(value, operator_slug, request), operator_slug, request)

    def get_filter_term(self, value, operator_slug, request):
        """
        :return: returns Q object or dictionary that will be used for filtering resource response.
        """
        raise NotImplementedError


class WildcardElasticsearchFilter(ElasticsearchFilter):

    allowed_operators = (OperatorSlug.CONTAINS, OperatorSlug.EQ)

    def clean_value(self, value, operator_slug, request):
        if operator_slug == OperatorSlug.EQ:
            return value
        else:
            return '*{}*'.format(value.replace('*', '\\*').replace('?', '\\?'))

    def get_filter_term(self, value, operator_slug, request):
        return Q('term' if operator_slug == OperatorSlug.EQ else 'wildcard', **{self.get_full_filter_key(): value})


class MatchElasticsearchFilter(ElasticsearchFilter):

    allowed_operators = (OperatorSlug.ICONTAINS,)

    def get_filter_term(self, value, operator_slug, request):
        return Q('match_phrase', **{self.get_full_filter_key(): value})


class BooleanElasticsearchFilter(BooleanFilterMixin, ElasticsearchFilter):

    allowed_operators = (OperatorSlug.EQ,)

    def get_filter_term(self, value, operator_slug, request):
        return Q('term', **{self.get_full_filter_key(): value})


class IDElasticsearchFilter(ElasticsearchFilter):

    allowed_operators = (OperatorSlug.EQ,)

    def get_filter_term(self, value, operator_slug, request):
        return Q('ids', **{'values': [value]})


class DateTimeElasticsearchFilter(DateFilterMixin, ElasticsearchFilter):

    suffixes = {}
    allowed_operators = (OperatorSlug.GT, OperatorSlug.GTE, OperatorSlug.LT, OperatorSlug.LTE)

    def get_filter_term(self, value, operator_slug, request):
        return Q('range', **{self.get_full_filter_key(): {operator_slug: value}})


class ElasticsearchFilterManager(BaseParserModelFilterManager):

    filter_by_field_name = {
        'text': MatchElasticsearchFilter,
        'jsontext': MatchElasticsearchFilter,
        'keyword': WildcardElasticsearchFilter,
        'boolean': BooleanElasticsearchFilter,
        'date': DateTimeElasticsearchFilter,
        'id': IDElasticsearchFilter,
    }

    def _logical_conditions_and(self, condition_a, condition_b):
        return condition_a & condition_b

    def _logical_conditions_or(self, condition_a, condition_b):
        return condition_a | condition_b

    def _logical_conditions_negation(self, condition):
        return ~condition

    def _get_model_filter(self, identifiers_prefix, identifiers, model, resource, request, filters_fields_rfs):
        current_identifier = self._get_real_field_name(resource, identifiers[0])
        identifiers_suffix = identifiers[1:]

        if current_identifier in filters_fields_rfs and not identifiers_prefix and not identifiers_suffix:
            try:
                if current_identifier == 'id':
                    field = None
                    field_name = 'id'
                else:
                    field = model._doc_type.mapping.properties[current_identifier]
                    field_name = field.name
                    if hasattr(field, 'builtin_type') and field_name not in self.filter_by_field_name:
                        field_name = field.builtin_type.name

                return self.filter_by_field_name[field_name](identifiers_prefix, identifiers, [], model, field=field)
            except KeyError:
                return None

        return None

    def _filter_queryset(self, qs, q):
        return qs.filter(q)
