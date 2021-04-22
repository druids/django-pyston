from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.core.validators import validate_ipv4_address, validate_ipv46_address
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import make_aware

from chamber.utils.datastructures import Enum

from dateutil.parser import DEFAULTPARSER

from pyston.utils import LOOKUP_SEP

from .exceptions import FilterValueError, OperatorFilterError


OPERATORS = Enum(
    ('GT', 'gt'),
    ('LT', 'lt'),
    ('EQ', 'eq'),
    ('NEQ', 'neq'),
    ('LTE', 'lte'),
    ('GTE', 'gte'),
    ('CONTAINS', 'contains'),
    ('ICONTAINS', 'icontains'),
    ('RANGE', 'range'),
    ('EXACT', 'exact'),
    ('IEXACT', 'iexact'),
    ('STARTSWITH', 'startswith'),
    ('ISTARTSWITH', 'istartswith'),
    ('ENDSWITH', 'endswith'),
    ('IENDSWITH', 'iendswith'),
    ('IN', 'in'),
    ('RANGE', 'range'),
    ('ALL', 'all'),
    ('ISNULL', 'isnull'),
)


NONE_LABEL = _('(None)')


class Operator:
    """
    Operator is used for specific type of filters that allows more different ways how to filter queryset data according
    to input operator between identifier and value.
    """

    def get_q(self, value, request):
        """
        Method must be implemented inside descendant and should return django db Q object that will be used for purpose
        of filtering queryset.
        """
        raise NotImplementedError


class EqualOperator(Operator):
    """
    Equal operator returns Q object that filter data if cleaned value is equal to DB object.
    """

    def get_q(self, filter, value, operator_slug, request):
        return Q(**{filter.get_full_filter_key(): filter.clean_value(value, operator_slug, request)})


class NotEqualOperator(Operator):
    """
    Not equal operator is opposite to equal operator.
    """

    def get_q(self, filter, value, operator_slug, request):
        return ~Q(**{filter.get_full_filter_key(): filter.clean_value(value, operator_slug, request)})


class SimpleOperator(Operator):
    """
    Simple operator is used for more operators that differ (in a DB view) only with string ORM operator.
    """

    def __init__(self, orm_operator):
        self.orm_operator = orm_operator

    def get_q(self, filter, value, operator_slug, request):
        value = filter.clean_value(value, operator_slug, request)
        return Q(**{'{}__{}'.format(filter.get_full_filter_key(), self.orm_operator): value})


class ListOperatorMixin:
    """
    The mixin is helper for operator objects that accepts list of data.
    It adds clean method that cleans list of values and returns an error to the concrete item of the list.
    """

    def _clean_list_values(self, filter, operator_slug, request, values):
        cleaned_values = []
        i = 0
        for value in values:
            try:
                cleaned_values.append(filter.clean_value(value, operator_slug, request))
            except FilterValueError as ex:
                raise FilterValueError(ugettext('Invalid value inside list at position {}, {}').format(i, ex))
            i += 1
        return cleaned_values


class SimpleListOperator(ListOperatorMixin, Operator):
    """
    The operator object is alternative to the Simple operator. It only accepts data in list format.
    """

    def __init__(self, orm_operator):
        self.orm_operator = orm_operator

    def get_q(self, filter, values, operator_slug, request):
        if not isinstance(values, list):
            raise FilterValueError(ugettext('Value must be list'))
        else:
            values = self._clean_list_values(filter, operator_slug, request, values)
        q = Q(**{
            '{}__{}'.format(filter.get_full_filter_key(), self.orm_operator): {v for v in values if values is not None}
        })
        if None in values:
            q |= Q(**{'{}__isnull'.format(filter.get_full_filter_key()): True})
        return q


class RangeOperator(ListOperatorMixin, Operator):
    """
    Operator filters range between two input values.
    """

    def get_q(self, filter, values, operator_slug, request):
        if not isinstance(values, list) or not len(values) != 2:
            raise FilterValueError(ugettext('Value must be list with two values'))
        else:
            values = self._clean_list_values(filter, operator_slug, request, values)
        return Q(**{'{}__range'.format(filter.get_full_filter_key()): values})


class AllListOperator(ListOperatorMixin, Operator):
    """
    Operator that is used for filtering m2m or m2o relations. All sent values must be related.
    """

    def get_q(self, filter, values, operator_slug, request):
        if not isinstance(values, list):
            raise FilterValueError(ugettext('Value must be list'))
        else:
            values = self._clean_list_values(filter, operator_slug, request, values)

        qs_obj_with_all_values = filter.field.model.objects.all()
        for v in set(values):
            qs_obj_with_all_values = qs_obj_with_all_values.filter(**{filter.identifiers[-1]: v})
        return Q(
            **{
                '{}__in'.format(
                    LOOKUP_SEP.join(filter.identifiers[:-1] + ['pk'])
                ): qs_obj_with_all_values.values('pk')
            }
        )


class DateContainsOperator(Operator):
    """
    Specific operator for datetime that allows filter date or datetime that is not fully sent.
    For example filter according to month and year (1.2017).
    """

    def get_q(self, filter, value, operator_slug, request):
        filter_term = {}
        value = filter.clean_value(value, operator_slug, request)
        for attr in filter.get_suffixes():
            date_val = getattr(value, attr)
            if date_val:
                filter_term[LOOKUP_SEP.join((filter.get_full_filter_key(), attr))] = date_val
        return Q(**filter_term)


EQ = EqualOperator()
NEQ = NotEqualOperator()
LT = SimpleOperator('lt')
GT = SimpleOperator('gt')
LTE = SimpleOperator('lte')
GTE = SimpleOperator('gte')
CONTAINS = SimpleOperator('contains')
ICONTAINS = SimpleOperator('icontains')
EXACT = SimpleOperator('exact')
IEXACT = SimpleOperator('iexact')
STARTSWITH = SimpleOperator('startswith')
ISTARTSWITH = SimpleOperator('istartswith')
ENDSWITH = SimpleOperator('endswith')
IENDSWITH = SimpleOperator('iendswith')
IN = SimpleListOperator('in')
RANGE = RangeOperator()
ALL = AllListOperator()
DATE_CONTAINS = DateContainsOperator()
PK_CONTAINS = SimpleOperator('pk__contains')
PK_ICONTAINS = SimpleOperator('pk__icontains')


class Filter:
    """
    Filters purpose is return Q object that is used for filtering data that resource returns.
    Filter can be joined to the field, method or resource.
    """

    suffixes = {}
    choices = None

    def __init__(self, identifiers_prefix, identifiers, identifiers_suffix, model, field=None, method=None):
        """
        Filter init values are these:
        :param identifiers_prefix: because filters are recursive if model relations property contains list of
               identifiers that was used for recursive searching the filter.
        :param identifiers: list of identifiers that conclusively identifies the filter.
        :param identifiers_suffix: list of suffixes that can be used for more specific filters.
               For example for a date filter can be used suffixes month, day, year.
        :param model: Django model class of filtered object.
        :param field: model field which is related with filter.
        :param method: method that is related with filter.
        method and field cannot be set together.
        """
        assert field is None or method is None, 'Field and method cannot be set together'

        self.identifiers_prefix = identifiers_prefix
        self.identifiers = identifiers
        self.identifiers_suffix = identifiers_suffix
        self.full_identifiers = identifiers_prefix + identifiers + identifiers_suffix
        self.field = field
        self.method = method
        self.model = model

    def get_allowed_operators(self):
        """
        :return: list of allowed operators to the concrete filter.
        """
        return self.allowed_operators

    @classmethod
    def get_suffixes(cls):
        """
        :return: set of allowed suffixes for the operator.
        """
        return cls.suffixes

    def get_q(self, value, operator_slug, request):
        """
        Method must be implemented inside descendant and should return django db Q object that will be used for purpose
        of filtering rest response data.
        """
        raise NotImplementedError


class OperatorsFilterMixin:
    """
    Mixin is used for specific type of filter that uses operator objects.
    """

    operators = ()

    def clean_value(self, value, operator_slug, request):
        """
        Method that cleans input value to the filter specific format.
        """
        return value

    def get_allowed_operators(self):
        return [operator_key for operator_key, operator in self.operators]

    def get_operator_obj(self, operator_slug):
        """
        :return: concrete operator object for the specific operator key.
        """
        operator_obj = dict(self.operators).get(operator_slug)
        if not operator_obj:
            raise OperatorFilterError
        return operator_obj

    def get_full_filter_key(self):
        return LOOKUP_SEP.join(self.full_identifiers)

    def get_q(self, value, operator_slug, request):
        operator_obj = self.get_operator_obj(operator_slug)
        return operator_obj.get_q(self, value, operator_slug, request)


class MethodFilter(Filter):
    """
    Abstract parent for all method filters.
    """

    def __init__(self, identifiers_prefix, identifiers, identifiers_suffix, model, method=None):
        assert method, 'Method is required'
        super(MethodFilter, self).__init__(identifiers_prefix, identifiers, identifiers_suffix, model, method=method)


class ModelFieldFilter(Filter):
    """
    Abstract parent for all model field filters.
    """

    def __init__(self, identifiers_prefix, identifiers, identifiers_suffix, model, field=None):
        assert field, 'Field is required'
        super(ModelFieldFilter, self).__init__(identifiers_prefix, identifiers, identifiers_suffix, model, field=field)


class OperatorsModelFieldFilter(OperatorsFilterMixin, ModelFieldFilter):
    pass


class BooleanFilterMixin:
    """
    Helper that contains cleaner for boolean input values.
    """

    choices = (
        (1, _('Yes')),
        (0, _('No'))
    )

    def clean_value(self, value, operator_slug, request):
        if isinstance(value, bool):
            return value
        elif value in {'true', 'false'}:
            return value == 'true'
        elif value in {'0', '1'}:
            return value == '1'
        else:
            raise FilterValueError(ugettext('Value must be boolean'))


class NullBooleanFilterMixin(BooleanFilterMixin):
    """
    Helper that contains cleaner for boolean input values where value can be None.
    """

    choices = (
        (None, NONE_LABEL),
        (1, _('Yes')),
        (0, _('No'))
    )

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        else:
            return super(NullBooleanFilterMixin, self).clean_value(value, operator_slug, request)


class BooleanFieldFilter(BooleanFilterMixin, OperatorsModelFieldFilter):

    operators = (
        (OPERATORS.EQ, EQ),
        (OPERATORS.NEQ, NEQ),
        (OPERATORS.LT, LT),
        (OPERATORS.GT, GT),
    )


class NullBooleanFieldFilter(NullBooleanFilterMixin, OperatorsModelFieldFilter):

    operators = (
        (OPERATORS.EQ, EQ),
        (OPERATORS.NEQ, NEQ),
        (OPERATORS.LT, LT),
        (OPERATORS.GT, GT),
    )


class NumberFieldFilter(OperatorsModelFieldFilter):

    operators = (
        (OPERATORS.EQ, EQ),
        (OPERATORS.NEQ, NEQ),
        (OPERATORS.LT, LT),
        (OPERATORS.GT, GT),
        (OPERATORS.LTE, LTE),
        (OPERATORS.GTE, GTE),
        (OPERATORS.IN, IN),
    )


class IntegerFieldFilterMixin:
    """
    Helper that contains cleaner for integer input values.
    """

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        try:
            return int(value)
        except (ValueError, TypeError):
            raise FilterValueError(ugettext('Value must be integer'))


class IntegerFieldFilter(IntegerFieldFilterMixin, NumberFieldFilter):
    pass


class FloatFieldFilter(NumberFieldFilter):

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        try:
            return float(value)
        except (ValueError, TypeError):
            raise FilterValueError(ugettext('Value must be float'))


class DecimalFieldFilter(NumberFieldFilter):

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        try:
            return Decimal(value)
        except InvalidOperation:
            raise FilterValueError(ugettext('Value must be decimal'))


class StringFieldFilter(OperatorsModelFieldFilter):

    operators = (
        (OPERATORS.ICONTAINS, ICONTAINS),
        (OPERATORS.CONTAINS, CONTAINS),
        (OPERATORS.EXACT, EXACT),
        (OPERATORS.IEXACT, IEXACT),
        (OPERATORS.STARTSWITH, STARTSWITH),
        (OPERATORS.ISTARTSWITH, ISTARTSWITH),
        (OPERATORS.ENDSWITH, ENDSWITH),
        (OPERATORS.IENDSWITH, IENDSWITH),
        (OPERATORS.EQ, EQ),
        (OPERATORS.NEQ, NEQ),
        (OPERATORS.LT, LT),
        (OPERATORS.GT, GT),
        (OPERATORS.LTE, LTE),
        (OPERATORS.GTE, GTE),
        (OPERATORS.IN, IN),
    )


class CaseSensitiveStringFieldFilter(StringFieldFilter):

    operators = (
        (OPERATORS.CONTAINS, CONTAINS),
        (OPERATORS.EXACT, EXACT),
        (OPERATORS.STARTSWITH, STARTSWITH),
        (OPERATORS.ENDSWITH, ENDSWITH),
        (OPERATORS.EQ, EQ),
        (OPERATORS.NEQ, NEQ),
        (OPERATORS.LT, LT),
        (OPERATORS.GT, GT),
        (OPERATORS.LTE, LTE),
        (OPERATORS.GTE, GTE),
        (OPERATORS.IN, IN),
    )


class IPAddressFilterFilter(CaseSensitiveStringFieldFilter):

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        elif operator_slug not in {OPERATORS.CONTAINS, OPERATORS.EXACT, OPERATORS.STARTSWITH, OPERATORS.ENDSWITH}:
            try:
                validate_ipv4_address(value)
            except ValidationError:
                raise FilterValueError(ugettext('Value must be in format IPv4.'))
        return value


class GenericIPAddressFieldFilter(CaseSensitiveStringFieldFilter):

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        elif operator_slug not in {OPERATORS.CONTAINS, OPERATORS.EXACT, OPERATORS.STARTSWITH, OPERATORS.ENDSWITH}:
            try:
                validate_ipv46_address(value)
            except ValidationError:
                raise FilterValueError(ugettext('Value must be in format IPv4 or IPv6.'))
        return value


class DateFilterMixin:

    suffixes = {
        'day', 'month', 'year'
    }

    def _clean_datetime_to_parts(self, value):
        value = DEFAULTPARSER._parse(value, dayfirst='-' not in value)
        value = value[0] if isinstance(value, tuple) else value

        if value is None:
            raise FilterValueError(ugettext('Value cannot be parsed to partial datetime'))
        else:
            return value

    def _clean_integer(self, value):
        try:
            return int(value)
        except ValueError:
            raise FilterValueError(ugettext('Value must be integer'))

    def _clean_datetime(self, value):
        try:
            datetime_value = DEFAULTPARSER.parse(value, dayfirst='-' not in value)
            return make_aware(datetime_value, is_dst=True) if datetime_value.tzinfo is None else datetime_value
        except ValueError:
            raise FilterValueError(ugettext('Value must be in format ISO 8601.'))

    def clean_value(self, value, operator_slug, request):
        suffix = self.identifiers_suffix[0] if self.identifiers_suffix else None
        if suffix in self.suffixes:
            return self._clean_integer(value)
        elif operator_slug == OPERATORS.CONTAINS:
            return self._clean_datetime_to_parts(value)
        elif value is None:
            return value
        else:
            return self._clean_datetime(value)


class DateFilter(DateFilterMixin, OperatorsModelFieldFilter):

    operators = (
        (OPERATORS.CONTAINS, DATE_CONTAINS),
        (OPERATORS.EQ, EQ),
        (OPERATORS.NEQ, NEQ),
        (OPERATORS.LT, LT),
        (OPERATORS.GT, GT),
        (OPERATORS.LTE, LTE),
        (OPERATORS.GTE, GTE),
        (OPERATORS.IN, IN),
    )


class DateTimeFilter(DateFilter):

    suffixes = {
        'day', 'month', 'year', 'hour', 'minute', 'second'
    }


class RelatedFieldFilter(OperatorsModelFieldFilter):
    """
    Helper that is used for relation model filters.
    """

    def get_last_rel_field(self, field):
        """
        :return: field that can be used for filtering of the relation filter.
        """
        if not field.is_relation:
            return field
        else:
            next_field = field.related_model._meta.get_field(field.remote_field.field_name)
            return self.get_last_rel_field(next_field)


class ForeignKeyFilter(RelatedFieldFilter):

    operators = (
        (OPERATORS.EQ, EQ),
        (OPERATORS.NEQ, NEQ),
        (OPERATORS.LT, LT),
        (OPERATORS.GT, GT),
        (OPERATORS.LTE, LTE),
        (OPERATORS.GTE, GTE),
        (OPERATORS.IN, IN),
        (OPERATORS.CONTAINS, PK_CONTAINS),
        (OPERATORS.ICONTAINS, PK_ICONTAINS),
    )

    def clean_value(self, value, operator_slug, request):
        if value is None or operator_slug in {OPERATORS.CONTAINS, OPERATORS.ICONTAINS}:
            return value
        try:
            return self.get_last_rel_field(self.field).get_prep_value(value)
        except ValueError:
            raise FilterValueError(ugettext('Object with this PK cannot be found'))


class ManyToManyFieldFilter(RelatedFieldFilter):

    operators = (
        (OPERATORS.EQ, EQ),
        (OPERATORS.IN, IN),
        (OPERATORS.ALL, ALL),
        (OPERATORS.CONTAINS, PK_CONTAINS),
        (OPERATORS.ICONTAINS, PK_ICONTAINS),
    )

    def clean_value(self, value, operator_slug, request):
        if value is None or operator_slug in {OPERATORS.CONTAINS, OPERATORS.ICONTAINS}:
            return value
        try:
            return self.get_last_rel_field(
                self.field.related_model._meta.get_field(self.field.related_model._meta.pk.name)
            ).get_prep_value(value)
        except ValueError:
            raise FilterValueError(ugettext('Object with this PK cannot be found'))


class ForeignObjectRelFilter(RelatedFieldFilter):

    operators = (
        (OPERATORS.EQ, EQ),
        (OPERATORS.IN, IN),
        (OPERATORS.ALL, ALL),
        (OPERATORS.CONTAINS, PK_CONTAINS),
        (OPERATORS.ICONTAINS, PK_ICONTAINS),
    )

    def clean_value(self, value, operator_slug, request):
        if value is None or operator_slug in {OPERATORS.CONTAINS, OPERATORS.ICONTAINS}:
            return value
        try:
            return self.get_last_rel_field(
                self.field.related_model._meta.get_field(self.field.related_model._meta.pk.name)
            ).get_prep_value(value)
        except ValueError:
            raise FilterValueError(ugettext('Object with this PK cannot be found'))


class SimpleFilterMixin:
    """
    Helper that is used for implementation all simple custom filters.
    """

    allowed_operators = None

    def _update_q_with_prefix(self, q):
        """
        Because implementation of custom filter should be as simple as possible this methods add identifier prefixes
        to the Q objects.
        """
        if isinstance(q, Q):
            q.children = [self._update_q_with_prefix(child) for child in q.children]
            return q
        else:
            return (
                LOOKUP_SEP.join((filter_part for filter_part in self.identifiers_prefix + [q[0]] if filter_part)), q[1]
            )

    def get_q(self, value, operator_slug, request):
        if operator_slug not in self.get_allowed_operators():
            raise OperatorFilterError
        else:
            filter_term = self.get_filter_term(self.clean_value(value, operator_slug, request), operator_slug, request)
            return self._update_q_with_prefix(Q(**filter_term) if isinstance(filter_term, dict) else filter_term)

    def clean_value(self, value, operator_slug, request):
        return value

    def get_allowed_operators(self):
        return self.allowed_operators

    def get_filter_term(self, value, operator_slug, request):
        """
        :return: returns Q object or dictionary that will be used for filtering resource response.
        """
        raise NotImplementedError


class SimpleEqualFilterMixin(SimpleFilterMixin):
    """
    Helper that allows filter only with operator equal (=).
    """

    allowed_operators = (OPERATORS.EQ,)


class SimpleFilter(SimpleFilterMixin, Filter):
    """
    Combination of filter and simple filter used for custom resource filters.
    """
    pass


class SimpleMethodFilter(SimpleFilterMixin, MethodFilter):
    """
    Combination of method filter and simple filter used for custom method filters.
    """
    pass


class SimpleModelFieldFilter(SimpleFilterMixin, ModelFieldFilter):
    """
    Combination of model field filter and simple filter used for custom model field filters.
    """
    pass


class SimpleEqualFilter(SimpleEqualFilterMixin, Filter):
    """
    Combination of simple equal filter and simple filter used for custom resource filters.
    """
    pass


class SimpleMethodEqualFilter(SimpleEqualFilterMixin, MethodFilter):
    """
    Combination of simple equal filter and method filter used for custom method filters.
    """
    pass


class SimpleModelFieldEqualFilter(SimpleEqualFilterMixin, ModelFieldFilter):
    """
    Combination of simple equal filter and model field filter used for custom model field filters.
    """
    pass
