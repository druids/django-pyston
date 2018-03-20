import re

import pyparsing as pp

from django.utils.safestring import mark_safe
from django.utils.translation import ugettext

from pyston.utils import LOOKUP_SEP

from .default_filters import OPERATORS
from .exceptions import FilterValueError, OperatorFilterError, FilterIdentifierError
from .utils import LOGICAL_OPERATORS


class FilterParserError(Exception):
    """
    Exception that is raised if filter input is invalid.
    """
    pass


class Condition:
    """
    Logical condition tree node.
    """

    def __init__(self, is_composed):
        self.is_composed = is_composed


class ComposedCondition(Condition):
    """
    Composed logical condition tree node. Contains operator (AND, OR, NOT), left and right condition that can be Term
    or ComposedCondition.
    """

    def __init__(self, operator_slug, condition_right, condition_left=None):
        super(ComposedCondition, self).__init__(True)
        self.operator_slug = operator_slug
        self.condition_left = condition_left
        self.condition_right = condition_right
        self.logical_condition = True


class Term(Condition):
    """
    Simple term. Contains operator (=, >, <, =>, contains, in, all, etc.), filter identifiers, value and source input
    value which is used to assemble error messages.
    """

    def __init__(self, operator_slug, identifiers, value, source):
        super(Term, self).__init__(False)
        self.operator_slug = operator_slug
        self.identifiers = identifiers
        self.value = value
        self.source = source


class FilterParser:
    """
    Abstract filter parser.
    """

    def parse(self, request):
        """
        :param request: Django HTTP request.
        :return: returns conditions tree or None.
        """
        raise NotImplementedError


class DefaultFilterParser(FilterParser):
    """
    Parser for complex filter terms.
    E.q.:
       /api/user?filter=created_at__moth=5 AND NOT (contract=null OR first_name='Petr')
    """

    ALLOWED_OPERATORS = (
        '=',
        '!=',
        '>=',
        '<=',
        '>',
        '<',
        '[a-z]+'
    )
    OPERATORS_MAPPING = {
        '=': OPERATORS.EQ,
        '!=': OPERATORS.NEQ,
        '<': OPERATORS.LT,
        '>': OPERATORS.GT,
        '>=': OPERATORS.GTE,
        '<=': OPERATORS.LTE,
    }
    VALUE_MAPPERS = {
        'null': None
    }

    def _clean_value(self, value):
        if isinstance(value, list):
            return [self._clean_value(v) for v in value]
        else:
            return self.VALUE_MAPPERS.get(value, value)

    def _clean_operator(self, operator_slug):
        return self.OPERATORS_MAPPING.get(operator_slug, operator_slug.lower())

    def _parse_to_conditions(self, parsed_result_list, condition_positions, condition, input):
        def _parse_to_conditions_recursive(term):
            if len(term) == 2 and term[0] == LOGICAL_OPERATORS.NOT:
                return LogicalCondition(LOGICAL_OPERATORS.NOT, _parse_to_conditions(term[1]))
            elif len(term) == 3 and term[1] in {LOGICAL_OPERATORS.AND, LOGICAL_OPERATORS.OR}:
                return ComposedCondition(
                    term[1],
                    _parse_to_conditions_recursive(term[2]),
                    _parse_to_conditions_recursive(term[0])
                )
            else:
                position = condition_positions.pop(0)
                from_position, to_position = next(condition.scanString(input[position:]))[1:]
                return Term(
                    self._clean_operator(term[1]),
                    term[0],
                    self._clean_value(term[2]),
                    input[position:][from_position:to_position]
                )
        return _parse_to_conditions_recursive(parsed_result_list)

    def parse(self, request):
        input = request._rest_context.get('filter')
        if not input:
            return None

        condition_positions = []

        operator = pp.Regex('|'.join(self.ALLOWED_OPERATORS))
        number = pp.Regex(r"[+-]?\d+(:?\.\d*)?(:?[eE][+-]?\d+)?")

        AND = pp.Literal(LOGICAL_OPERATORS.AND)
        OR = pp.Literal(LOGICAL_OPERATORS.OR)
        NOT = pp.Literal(LOGICAL_OPERATORS.NOT)

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
        null = pp.Literal('null').setParseAction(lambda s,l,t: None)
        boolean = pp.Regex('|'.join(('true', 'false'))).setParseAction(lambda s, l, t: t[0] == 'true')

        comparison_term << (string | number | list_term | null | boolean)

        condition = pp.Group(identifiers + operator + comparison_term).setResultsName('condition')
        condition.setParseAction(lambda s, loc, tocs: condition_positions.append(loc))

        expr = pp.operatorPrecedence(
            condition, [
                (NOT, 1, pp.opAssoc.RIGHT,),
                (AND, 2, pp.opAssoc.LEFT,),
                (OR, 2, pp.opAssoc.LEFT,),
            ]
        )

        try:
            return self._parse_to_conditions(
                expr.parseString(input, parseAll=True).asList()[0], list(condition_positions), condition, input
            )
        except pp.ParseException as ex:
            raise FilterParserError(
                mark_safe(ugettext('Invalid filter value "{}"').format(input))
            )


class FlatAndFilterParser(FilterParser):
    """
    Helper used to implement parsers that join terms only with AND operator.
    """

    def _parse_to_composed_conditions(self, conditions_list):
        if len(conditions_list) == 1:
            return conditions_list[0]
        else:
            return ComposedCondition(LOGICAL_OPERATORS.AND, self._parse_to_composed_conditions(conditions_list[1:]),
                                     conditions_list[0])


class QueryStringFilterParser(FlatAndFilterParser):
    """
    Simple query string parser that parse input request query string to the conditions joined with AND operator.
    E.q.:
       /api/user?created_at__moth=5&contract=__none__
    """

    VALUE_MAPPERS = {
        '__none__': None
    }
    MULTIPLE_VALUES_OPERATORS = {
        OPERATORS.IN, OPERATORS.ALL
    }

    def _clean_multiple_values(self, operator_slug, value):
        for pattern in ('\[(.*)\]', '\((.*)\)', '\{(.*)\}'):
            m = re.compile(pattern).match(value)
            if m:
                return [self._clean_simple_value(v) for v in m.group(1).split(',')] if m.group(1) else []

        raise FilterParserError('Value must be in list "[]", tuple "()" or set "{}" format split with char ",".')

    def _clean_simple_value(self, value):
        return self.VALUE_MAPPERS.get(value, value)

    def _clean_value(self, operator_slug, value):
        if operator_slug.lower() in self.MULTIPLE_VALUES_OPERATORS:
            return self._clean_multiple_values(operator_slug, value)
        else:
            return self._clean_simple_value(value)

    def _parse_to_composed_conditions(self, conditions_list):
        if len(conditions_list) == 1:
            return conditions_list[0]
        else:
            return ComposedCondition(LOGICAL_OPERATORS.AND, self._parse_to_composed_conditions(conditions_list[1:]),
                                     conditions_list[0])

    def parse(self, request):
        filter_terms_with_values = [
            (filter_term, value) for filter_term, value in request.GET.dict().items()
            if not filter_term.startswith('_') and filter_term not in request._rest_context
        ]
        if not filter_terms_with_values:
            return None

        conditions_list = []
        for filter_term, value in filter_terms_with_values:
            identifiers = filter_term.split(LOOKUP_SEP)

            if len(identifiers) > 1 and identifiers[-1].upper() == LOGICAL_OPERATORS.NOT:
                identifiers = identifiers[:-1]
                exclude = True
            else:
                exclude = False

            if len(identifiers) > 1 and identifiers[-1].lower() in OPERATORS:
                operator_slug = identifiers[-1].lower()
                identifiers = identifiers[:-1]
            else:
                operator_slug = OPERATORS.EQ

            try:
                cleaned_value = self._clean_value(operator_slug, value)
            except FilterParserError as ex:
                raise FilterParserError(
                    'Invalid filter term {}. {}'.format('{}={}'.format(filter_term, value), ex)
                )

            condition = Term(operator_slug, identifiers, cleaned_value, '{}={}'.format(filter_term, value))
            if exclude:
                condition = ComposedCondition(LOGICAL_OPERATORS.NOT, condition)
            conditions_list.append(condition)
        return self._parse_to_composed_conditions(conditions_list)
