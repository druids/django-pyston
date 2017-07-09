from __future__ import unicode_literals

from django.db.models import Q
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext

from chamber.utils.datastructures import Enum

from pyston.exception import RESTException
from pyston.utils import rfs
from pyston.utils.helpers import get_field_or_none, get_method_or_none
from pyston.serializer import get_resource_or_none

from .default_filters import OPERATORS
from .exceptions import FilterValueException, OperatorFilterException, FilterIdentifierException

import pyparsing as pp


LOGICAL_OPERATORS = Enum(
    'AND',
    'OR',
    'NOT',
)


class Condition(object):

    def __init__(self, is_composed):
        self.is_composed = is_composed


class ComposedCondition(Condition):

    def __init__(self, operator, condition_right, condition_left=None):
        super(ComposedCondition, self).__init__(True)
        self.operator = operator
        self.condition_left = condition_left
        self.condition_right = condition_right
        self.logical_condition = True


class Term(Condition):

    def __init__(self, operator, identifiers, value, source):
        super(Term, self).__init__(False)
        self.operator = operator
        self.identifiers = identifiers
        self.value = value
        self.source = source


class DefaultFilterParser(object):

    OPERATORS = (
        '=',
        '!=',
        '>',
        '<',
        '>=',
        '<=',
        '[a-z]+'
    )

    def parse_to_conditions(self, parsed_result_list, condition_positions):
        def _parse_to_conditions(term):
            if len(term) == 2 and term[0] == LOGICAL_OPERATORS.NOT:
                return LogicalCondition(LOGICAL_OPERATORS.NOT, _parse_to_conditions(term[1]))
            elif len(term) == 3 and term[1] in {LOGICAL_OPERATORS.AND, LOGICAL_OPERATORS.OR}:
                return ComposedCondition(
                    term[1],
                    _parse_to_conditions(term[2]),
                    _parse_to_conditions(term[0])
                )
            else:
                position = condition_positions.pop(0)
                from_position, to_position = next(condition.scanString(input[position:]))[1:]
                return Term(
                    term[1],
                    term[0],
                    term[2],
                    input[position:][from_position:to_position]
                )
        return _parse_to_conditions(parsed_result_list)

    def parse(self, input):
        condition_positions = []

        operator = pp.Regex('|'.join(self.OPERATORS))
        number = pp.Regex(r"[+-]?\d+(:?\.\d*)?(:?[eE][+-]?\d+)?")

        AND = pp.Literal(LOGICAL_OPERATORS.AND).setResultsName('logical_operator')
        OR = pp.Literal(LOGICAL_OPERATORS.OR).setResultsName('logical_operator')
        NOT = pp.Literal(LOGICAL_OPERATORS.NOT).setResultsName('logical_operator')

        identifier = pp.Regex(r"[a-zA-Z]+[a-zA-Z0-9]*(_[a-zA-Z0-9]+)*")
        identifiers = pp.Group(pp.delimitedList(identifier, delim="__", combine=False))

        comparison_term = pp.Forward()
        list_term = (
            pp.Group(
                pp.Suppress('[') + pp.delimitedList(comparison_term, delim=",", combine=False) + pp.Suppress(']')
            ) |
            pp.Group(
                pp.Suppress('(') + pp.delimitedList(comparison_term, delim=",", combine=False) + pp.Suppress(')')
            ) |
            pp.Group(
                pp.Suppress('{') + pp.delimitedList(comparison_term, delim=",", combine=False) + pp.Suppress('}')
            )
        )
        string = (
            pp.QuotedString("'", escChar='\\', unquoteResults=True) | pp.QuotedString('"', escChar='\\',
                                                                                      unquoteResults=True)
        )

        comparison_term << (string | number | list_term)

        condition = pp.Group(identifiers + operator + comparison_term).setResultsName('condition')
        condition.setParseAction(lambda s, loc, tocs: condition_positions.append(loc))

        expr = pp.operatorPrecedence(
            condition, [
                (NOT, 1, pp.opAssoc.RIGHT,),
                (AND, 2, pp.opAssoc.LEFT,),
                (OR, 2, pp.opAssoc.LEFT,),
            ]
        ).setResultsName('term')

        return self.parse_to_conditions(expr.parseString(input, parseAll=True).asList()[0], list(condition_positions))


class ModelFilterManager(object):

    def _get_method_filter_class(self, identifiers, method):
        if not hasattr(method, 'filter'):
            raise FilterIdentifierException
        return method.filter(identifiers, method=method)

    def _get_resource_filter(self, full_identifiers, identifiers, model, resource, request, filters_fields_rfs):
        identifiers_string = '__'.join(identifiers)
        current_identifier = identifiers[0]
        resource_method = get_method_or_none(resource, current_identifier)
        if resource and identifiers_string in resource.filters:
            return resource.filters[identifiers_string](full_identifiers)
        elif current_identifier in filters_fields_rfs and resource_method:
            return self._get_method_filter_class(full_identifiers, resource_method)
        else:
            return None

    def _get_model_filter(self, full_identifiers, identifiers, model, resource, request, filters_fields_rfs):
        current_identifier = identifiers[0]

        if current_identifier not in filters_fields_rfs:
            raise FilterIdentifierException

        suffix = '__'.join(identifiers[1:])

        model_field = get_field_or_none(model, current_identifier)
        model_method = get_method_or_none(model, current_identifier)

        if model_field and model_field.filter and (not suffix or suffix in model_field.filter.get_suffixes()):
            return model_field.filter(full_identifiers, field=model_field)
        elif model_field and model_field.is_relation and model_field.related_model:
            next_model = model_field.related_model
            next_resource = get_resource_or_none(request, next_model, getattr(resource, 'resource_typemapper'))
            return self._get_filter_recursive(
                full_identifiers, identifiers[1:], next_model, next_resource, request,
                filters_fields_rfs[current_identifier].subfieldset
            )
        elif model_method:
            return self._get_method_filter_class(full_identifiers, model_method)

    def _get_filter_recursive(self, full_identifiers, identifiers, model, resource, request, extra_filter_fields=None):
        extra_filter_fields = rfs() if extra_filter_fields is None else extra_filter_fields
        filters_fields_rfs = (
            extra_filter_fields.join(resource.get_filter_fields_rfs()) if resource else extra_filter_fields
        )
        filter_obj = (
            self._get_resource_filter(
                full_identifiers, identifiers, model, resource, request, filters_fields_rfs) or
            self._get_model_filter(
                full_identifiers, identifiers, model, resource, request, filters_fields_rfs)
        )
        if not filter_obj:
            raise FilterIdentifierException
        return filter_obj

    def _get_filter(self, identifiers, resource, request):
        return self._get_filter_recursive(identifiers, identifiers, resource.model, resource, request)


class DefaultFilterManager(ModelFilterManager):

    OPERATORS_MAPPING = {
        '=': OPERATORS.EQ,
        '!=': OPERATORS.NEQ,
        '<': OPERATORS.LT,
        '>': OPERATORS.GT,
        '>=': OPERATORS.GTE,
        '<=': OPERATORS.LTE,
    }

    parser = DefaultFilterParser()

    def convert_term(self, condition, resource, request):
        if condition.is_composed and condition.operator == LOGICAL_OPERATORS.NOT:
            return ~Q(self.convert_term(condition.condition_right), resource, request)
        elif condition.is_composed and condition.operator == LOGICAL_OPERATORS.AND:
            return Q(self.convert_term(condition.condition_left, resource, request),
                     self.convert_term(condition.condition_right, resource, request))
        elif condition.is_composed and condition.operator == LOGICAL_OPERATORS.OR:
            return Q(self.convert_term(condition.condition_left, resource, request) |
                     self.convert_term(condition.condition_right, resource, request))
        else:
            try:
                return self._get_filter(condition.identifiers, resource, request).get_q(
                    condition.value, self.OPERATORS_MAPPING.get(condition.operator, condition.operator.upper()),
                    request
                )
            except FilterIdentifierException:
                raise RESTException(
                    mark_safe(ugettext('Invalid identifier of condition "{}"').format(condition.source))
                )
            except FilterValueException as ex:
                raise RESTException(
                    mark_safe(ugettext('Invalid value of condition "{}". {}').format(condition.source, ex))
                )
            except OperatorFilterException:
                raise RESTException(
                    mark_safe(ugettext('Invalid operator of condition "{}"').format(condition.source))
                )

    def filter(self, resource, qs, request):
        if 'filter' in request.GET:
            try:
                parsed_conditions = self.parser.parse(request.GET['filter'])
                return qs.filter(pk__in=qs.filter(self.convert_term(parsed_conditions, resource, request)).values('pk'))
            except pp.ParseException:
                raise RESTException(
                    mark_safe(ugettext('Invalid filter value "{}"').format(request.GET['filter']))
                )
        else:
            return qs


class GETListFilterManager(ModelFilterManager):

    def filter(self, resource, qs, request):
        filter_terms_with_values = [
            (filter_term, value) for filter_term, value in request.GET.dict().items()
            if not filter_term.startswith('_') and not filter_term == 'filter'
        ]
        qs_filter_terms = []
        for filter_term, value in filter_terms_with_values:
            filter_term_list = filter_term.split('__')

            if len(filter_term_list) > 1 and filter_term_list[-1].upper() in 'NOT':
                filter_term_list = filter_term_list[:-1]
                exclude = True
            else:
                exclude = False

            if len(filter_term_list) > 1 and filter_term_list[-1].upper() in OPERATORS:
                *filter_term_list, operator = filter_term_list
                operator = operator.upper()
            else:
                operator = OPERATORS.EQ

            try:
                q = self._get_filter(filter_term_list, resource, request).get_q(value, operator, request)
            except FilterIdentifierException:
                raise RESTException(mark_safe(ugettext('Cannot resolve filter "{}={}"').format(filter_term, value)))
            except FilterValueException as ex:
                raise RESTException(
                    mark_safe(ugettext('Invalid filter value "{}={}". {}').format(filter_term, value, ex))
                )
            except OperatorFilterException:
                raise RESTException(
                    mark_safe(ugettext('Invalid filter operator "{}={}".').format(filter_term, value))
                )

            qs_filter_terms.append(~Q(q) if exclude else q)

        return qs.filter(pk__in=qs.filter(*qs_filter_terms).values('pk')) if qs_filter_terms else qs


class MultipleFilterManager(ModelFilterManager):

    def filter(self, resource, qs, request):
        qs = DefaultFilterManager().filter(resource, qs, request)
        qs = GETListFilterManager().filter(resource, qs, request)
        return qs
