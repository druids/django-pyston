from django.db.models import (
    Q, AutoField, DateField, DateTimeField, DecimalField, GenericIPAddressField, IPAddressField, BooleanField,
    TextField, CharField, IntegerField, FloatField, SlugField, EmailField, NullBooleanField, UUIDField, JSONField
)
from django.db.models.fields.related import ForeignKey, ManyToManyField, ForeignObjectRel
from django.utils.translation import ugettext

from pyston.utils import LOOKUP_SEP

from .filters import (
    OperatorQuery, BooleanFilterMixin, NullBooleanFilterMixin, OperatorsModelFieldFilter,
    FloatFilterMixin, IntegerFilterMixin, DecimalFilterMixin,
    IPAddressFilterMixin, GenericIPAddressFilterMixin, DateFilterMixin,
    Filter, MethodFilter, ModelFieldFilter
)
from .exceptions import FilterValueError, OperatorFilterError
from .utils import OperatorSlug


class EqualOperatorQuery(OperatorQuery):
    """
    Equal operator returns Q object that filter data if cleaned value is equal to DB object.
    """

    def get_q(self, filter, value, operator_slug, request):
        return Q(**{filter.get_full_filter_key(): filter.clean_value(value, operator_slug, request)})


class NotEqualOperatorQuery(OperatorQuery):
    """
    Not equal operator is opposite to equal operator.
    """

    def get_q(self, filter, value, operator_slug, request):
        return ~Q(**{filter.get_full_filter_key(): filter.clean_value(value, operator_slug, request)})


class SimpleOperatorQuery(OperatorQuery):
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


class SimpleListOperatorQuery(ListOperatorMixin, OperatorQuery):
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


class RangeOperatorQuery(ListOperatorMixin, OperatorQuery):
    """
    Operator filters range between two input values.
    """

    def get_q(self, filter, values, operator_slug, request):
        if not isinstance(values, list) or not len(values) != 2:
            raise FilterValueError(ugettext('Value must be list with two values'))
        else:
            values = self._clean_list_values(filter, operator_slug, request, values)
        return Q(**{'{}__range'.format(filter.get_full_filter_key()): values})


class AllListOperatorQuery(ListOperatorMixin, OperatorQuery):
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


class DateContainsOperatorQuery(OperatorQuery):
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


EQ = EqualOperatorQuery()
NEQ = NotEqualOperatorQuery()
LT = SimpleOperatorQuery('lt')
GT = SimpleOperatorQuery('gt')
LTE = SimpleOperatorQuery('lte')
GTE = SimpleOperatorQuery('gte')
CONTAINS = SimpleOperatorQuery('contains')
ICONTAINS = SimpleOperatorQuery('icontains')
EXACT = SimpleOperatorQuery('exact')
IEXACT = SimpleOperatorQuery('iexact')
STARTSWITH = SimpleOperatorQuery('startswith')
ISTARTSWITH = SimpleOperatorQuery('istartswith')
ENDSWITH = SimpleOperatorQuery('endswith')
IENDSWITH = SimpleOperatorQuery('iendswith')
IN = SimpleListOperatorQuery('in')
RANGE = RangeOperatorQuery()
ALL = AllListOperatorQuery()
DATE_CONTAINS = DateContainsOperatorQuery()
PK_CONTAINS = SimpleOperatorQuery('pk__contains')
PK_ICONTAINS = SimpleOperatorQuery('pk__icontains')


class BooleanFieldFilter(BooleanFilterMixin, OperatorsModelFieldFilter):

    operators = (
        (OperatorSlug.EQ, EQ),
        (OperatorSlug.NEQ, NEQ),
        (OperatorSlug.LT, LT),
        (OperatorSlug.GT, GT),
    )


class NullBooleanFieldFilter(NullBooleanFilterMixin, OperatorsModelFieldFilter):

    operators = (
        (OperatorSlug.EQ, EQ),
        (OperatorSlug.NEQ, NEQ),
        (OperatorSlug.LT, LT),
        (OperatorSlug.GT, GT),
    )


class BaseNumberFieldFilter(OperatorsModelFieldFilter):

    operators = (
        (OperatorSlug.EQ, EQ),
        (OperatorSlug.NEQ, NEQ),
        (OperatorSlug.LT, LT),
        (OperatorSlug.GT, GT),
        (OperatorSlug.LTE, LTE),
        (OperatorSlug.GTE, GTE),
        (OperatorSlug.IN, IN),
    )


class IntegerFieldFilter(IntegerFilterMixin, BaseNumberFieldFilter):
    pass


class FloatFieldFilter(FloatFilterMixin, BaseNumberFieldFilter):
    pass


class DecimalFieldFilter(DecimalFilterMixin, BaseNumberFieldFilter):
    pass


class StringFieldFilter(OperatorsModelFieldFilter):

    operators = (
        (OperatorSlug.ICONTAINS, ICONTAINS),
        (OperatorSlug.CONTAINS, CONTAINS),
        (OperatorSlug.EXACT, EXACT),
        (OperatorSlug.IEXACT, IEXACT),
        (OperatorSlug.STARTSWITH, STARTSWITH),
        (OperatorSlug.ISTARTSWITH, ISTARTSWITH),
        (OperatorSlug.ENDSWITH, ENDSWITH),
        (OperatorSlug.IENDSWITH, IENDSWITH),
        (OperatorSlug.EQ, EQ),
        (OperatorSlug.NEQ, NEQ),
        (OperatorSlug.LT, LT),
        (OperatorSlug.GT, GT),
        (OperatorSlug.LTE, LTE),
        (OperatorSlug.GTE, GTE),
        (OperatorSlug.IN, IN),
    )


class CaseSensitiveStringFieldFilter(StringFieldFilter):

    operators = (
        (OperatorSlug.CONTAINS, CONTAINS),
        (OperatorSlug.EXACT, EXACT),
        (OperatorSlug.STARTSWITH, STARTSWITH),
        (OperatorSlug.ENDSWITH, ENDSWITH),
        (OperatorSlug.EQ, EQ),
        (OperatorSlug.NEQ, NEQ),
        (OperatorSlug.LT, LT),
        (OperatorSlug.GT, GT),
        (OperatorSlug.LTE, LTE),
        (OperatorSlug.GTE, GTE),
        (OperatorSlug.IN, IN),
    )


class IPAddressFieldFilter(IPAddressFilterMixin, CaseSensitiveStringFieldFilter):
    pass


class GenericIPAddressFieldFilter(GenericIPAddressFilterMixin, CaseSensitiveStringFieldFilter):
    pass


class DateFieldFilter(DateFilterMixin, OperatorsModelFieldFilter):

    operators = (
        (OperatorSlug.CONTAINS, DATE_CONTAINS),
        (OperatorSlug.EQ, EQ),
        (OperatorSlug.NEQ, NEQ),
        (OperatorSlug.LT, LT),
        (OperatorSlug.GT, GT),
        (OperatorSlug.LTE, LTE),
        (OperatorSlug.GTE, GTE),
        (OperatorSlug.IN, IN),
    )


class DateTimeFieldFilter(DateFieldFilter):

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


class ForeignKeyFieldFilter(RelatedFieldFilter):

    operators = (
        (OperatorSlug.EQ, EQ),
        (OperatorSlug.NEQ, NEQ),
        (OperatorSlug.LT, LT),
        (OperatorSlug.GT, GT),
        (OperatorSlug.LTE, LTE),
        (OperatorSlug.GTE, GTE),
        (OperatorSlug.IN, IN),
        (OperatorSlug.CONTAINS, PK_CONTAINS),
        (OperatorSlug.ICONTAINS, PK_ICONTAINS),
    )

    def clean_value(self, value, operator_slug, request):
        if value is None or operator_slug in {OperatorSlug.CONTAINS, OperatorSlug.ICONTAINS}:
            return value
        try:
            return self.get_last_rel_field(self.field).get_prep_value(value)
        except ValueError:
            raise FilterValueError(ugettext('Object with this PK cannot be found'))


class ManyToManyFieldFilter(RelatedFieldFilter):

    operators = (
        (OperatorSlug.EQ, EQ),
        (OperatorSlug.IN, IN),
        (OperatorSlug.ALL, ALL),
        (OperatorSlug.CONTAINS, PK_CONTAINS),
        (OperatorSlug.ICONTAINS, PK_ICONTAINS),
    )

    def clean_value(self, value, operator_slug, request):
        if value is None or operator_slug in {OperatorSlug.CONTAINS, OperatorSlug.ICONTAINS}:
            return value
        try:
            return self.get_last_rel_field(
                self.field.related_model._meta.get_field(self.field.related_model._meta.pk.name)
            ).get_prep_value(value)
        except ValueError:
            raise FilterValueError(ugettext('Object with this PK cannot be found'))


class ForeignObjectRelFilter(RelatedFieldFilter):

    operators = (
        (OperatorSlug.EQ, EQ),
        (OperatorSlug.IN, IN),
        (OperatorSlug.ALL, ALL),
        (OperatorSlug.CONTAINS, PK_CONTAINS),
        (OperatorSlug.ICONTAINS, PK_ICONTAINS),
    )

    def clean_value(self, value, operator_slug, request):
        if value is None or operator_slug in {OperatorSlug.CONTAINS, OperatorSlug.ICONTAINS}:
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

    def get_filter_term(self, value, operator_slug, request):
        """
        :return: returns Q object or dictionary that will be used for filtering resource response.
        """
        raise NotImplementedError


class SimpleEqualFilterMixin(SimpleFilterMixin):
    """
    Helper that allows filter only with operator equal (=).
    """

    allowed_operators = (OperatorSlug.EQ,)


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


default_django_model_field_filters = {
    BooleanField: BooleanFieldFilter,
    NullBooleanField: NullBooleanFieldFilter,
    TextField: StringFieldFilter,
    CharField: StringFieldFilter,
    IntegerField: IntegerFieldFilter,
    FloatField: FloatFieldFilter,
    DecimalField: DecimalFieldFilter,
    AutoField: IntegerFieldFilter,
    DateField: DateFieldFilter,
    DateTimeField: DateTimeFieldFilter,
    GenericIPAddressField: GenericIPAddressFieldFilter,
    IPAddressField: IPAddressFieldFilter,
    ManyToManyField: ManyToManyFieldFilter,
    ForeignKey: ForeignKeyFieldFilter,
    ForeignObjectRel: ForeignObjectRelFilter,
    SlugField: CaseSensitiveStringFieldFilter,
    EmailField: CaseSensitiveStringFieldFilter,
    UUIDField: StringFieldFilter,
    JSONField: StringFieldFilter
}


def register_default_field_filter_class(field_class, filter_class):
    default_django_model_field_filters[field_class] = filter_class


def get_default_field_filter_class(model_field):
    for field_class, filter_class in list(default_django_model_field_filters.items())[::-1]:
        if isinstance(model_field, field_class):
            return filter_class
    return None
