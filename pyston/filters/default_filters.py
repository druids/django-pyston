from __future__ import unicode_literals

import re

from decimal import Decimal, InvalidOperation

from django.utils.translation import ugettext
from django.utils.translation import ugettext_lazy as _
from django import forms
from django.db.models import Q
from django.db.models.fields import (AutoField, DateField, DateTimeField, DecimalField, GenericIPAddressField,
                                     IPAddressField, BooleanField, TextField, CharField, IntegerField, FloatField,
                                     SlugField, EmailField)
from django.db.models.fields.related import ForeignObjectRel, ManyToManyField, ForeignKey

from chamber.utils.datastructures import Enum

from dateutil.parser import DEFAULTPARSER

from .exceptions import FilterException, FilterValueException, OperatorFilterException

from chamber.utils.datetimes import make_aware


OPERATORS = Enum(
    'GT',
    'LT',
    'EQ',
    'NEQ',
    'LTE',
    'GTE',
    'CONTAINS',
    'ICONTAINS',
    'RANGE',
    'EXACT',
    'IEXACT',
    'STARTSWITH',
    'ISTARTSWITH',
    'ENDSWITH',
    'IENDSWITH',
    'IN',
    'RANGE',
    'ALL',
)


class Operator(object):

    def get_q(self, value, request):
        raise NotImplementedError


class EqualOperator(Operator):

    def get_q(self, filter, value, request):
        value = filter.clean_value(value, request)
        return Q(**{filter.get_full_filter_key(): value})


class NotEqualOperator(Operator):

    def get_q(self, filter, value, request):
        value = filter.clean_value(value, request)
        return ~Q(**{filter.get_full_filter_key(): value})


class SimpleOperator(Operator):

    def __init__(self, orm_operator):
        self.orm_operator = orm_operator

    def get_q(self, filter, value, request):
        value = filter.clean_value(value, request)
        print('{}__{}'.format(filter.get_full_filter_key(), self.orm_operator))
        return Q(**{'{}__{}'.format(filter.get_full_filter_key(), self.orm_operator): value})


class SimpleListOperator(Operator):

    def __init__(self, orm_operator):
        self.orm_operator = orm_operator

    def get_q(self, filter, values, request):
        if not isinstance(values, list):
            raise FilterValueException(ugettext('Value must be list'))
        else:
            values = [filter.clean_value(value, request) for value in values]
        return Q(**{'{}__{}'.format(filter.get_full_filter_key(), self.orm_operator): values})


class RangeOperator(Operator):

    def get_q(self, filter, values, request):
        if not isinstance(values, list) or not len(values) != 2:
            raise FilterValueException(ugettext('Value must be list with two values'))
        else:
            values = [filter.clean_value(value, request) for value in values]
        return Q(**{'{}__range'.format(filter.get_full_filter_key()): values})


class AllListOperator(Operator):

    def get_q(self, filter, values, request):
        if not isinstance(values, list):
            raise FilterValueException(ugettext('Value must be list'))
        else:
            values = [filter.clean_value(value, request) for value in values]

        qs_obj_with_all_values = self.field.model.objects.all()
        for v in set(values):
            qs_obj_with_all_values = qs_obj_with_all_values.filter(**{filter.identifiers[-1]: v})
        return {'{}__pk__in'.format('__'.join(filter.identifiers[:-1])): qs_obj_with_all_values.values('pk')}


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
IN = SimpleOperator('in')
RANGE = RangeOperator()
ALL = AllListOperator()


class Filter(object):

    widget = None
    suffixes = {}

    def __init__(self, identifiers):
        self.identifiers = identifiers

    @classmethod
    def get_suffixes(cls):
        return cls.suffixes

    def get_suffix(self):
        if self.identifiers[-1] in self.suffixes:
            return self.identifiers[-1]
        else:
            return None

    def get_widget(self, *args, **kwargs):
        return self.widget

    def get_q(self, value, operator, request):
        raise NotImplementedError

    def get_placeholder(self, request):
        return None

    def get_attrs_for_widget(self):
        return {'data-filter': self.get_filter_name()}

    def render(self, request):
        widget = self.get_widget(request)
        if not widget:
            return ''
        else:
            placeholder = self.get_placeholder(request)
            if placeholder:
                widget.placeholder = placeholder
            return widget.render('filter__{}'.format(self.get_filter_name()), None,
                                 attrs=self.get_attrs_for_widget())


class OperatorsFilter(Filter):

    operators = {}

    def clean_value(self, value, request):
        return value

    def get_operator_obj(self, operator):
        operator = self.operators.get(operator)
        if not operator:
            raise OperatorFilterException
        return operator

    def get_full_filter_key(self):
        return '__'.join(self.identifiers)

    def get_q(self, value, operator, request):
        operator = self.get_operator_obj(operator)
        return operator.get_q(self, value, request)


class MethodFilterMixin(object):

    def __init__(self, identifiers, method):
        super(MethodFilterMixin, self).__init__(identifiers)
        self.method = method

    def get_widget(self, request):
        if self.widget:
            return self.widget

        formfield = self.field.formfield()
        if formfield:
            if hasattr(formfield, 'choices') and formfield.choices:
                formfield.choices = list(formfield.choices)
                if not formfield.choices[0][0]:
                    del formfield.choices[0]
                formfield.choices.insert(0, ('', self.get_placeholder(request) or ''))
            return formfield.widget
        return forms.TextInput()


class ModelFieldFilterMixin(object):

    def __init__(self, identifiers, field):
        super(OperatorsModelFieldFilter, self).__init__(identifiers)
        self.field = field


class OperatorsModelFieldFilter(ModelFieldFilterMixin, OperatorsFilter):
    pass


class BooleanFieldFilter(OperatorsModelFieldFilter):

    widget = forms.Select(choices=(('', ''), (1, _('Yes')), (0, _('No'))))

    operators = {
        OPERATORS.EQ: EQ,
        OPERATORS.NEQ: NEQ,
        OPERATORS.LT: LT,
        OPERATORS.GT: GT,
    }

    def clean_value(self, value, request):
        if not isinstance(value, bool):
            raise FilterValueException(ugettext('Value must be boolean'))
        else:
            return value


class NumberFieldFilter(OperatorsModelFieldFilter):

    operators = {
        OPERATORS.EQ: EQ,
        OPERATORS.NEQ: NEQ,
        OPERATORS.LT: LT,
        OPERATORS.GT: GT,
        OPERATORS.LTE: LTE,
        OPERATORS.GTE: GTE,
        OPERATORS.IN: IN,
    }


class IntegerFieldFilter(NumberFieldFilter):

    def clean_value(self, value, request):
        try:
            return int(value)
        except ValueError:
            raise FilterValueException(ugettext('Value must be integer'))


class FloatFieldFilter(NumberFieldFilter):

    def clean_value(self, value, request):
        try:
            return float(value)
        except ValueError:
            raise FilterValueException(ugettext('Value must be float'))


class DecimalFieldFilter(NumberFieldFilter):

    def clean_value(self, value, request):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise FilterValueException(ugettext('Value must be decimal'))


class StringFieldFilter(OperatorsModelFieldFilter):

    operators = {
        OPERATORS.EQ: EQ,
        OPERATORS.NEQ: NEQ,
        OPERATORS.LT: LT,
        OPERATORS.GT: GT,
        OPERATORS.LTE: LTE,
        OPERATORS.GTE: GTE,
        OPERATORS.IN: IN,
        OPERATORS.CONTAINS: CONTAINS,
        OPERATORS.ICONTAINS: ICONTAINS,
        OPERATORS.EXACT: EXACT,
        OPERATORS.IEXACT: IEXACT,
        OPERATORS.STARTSWITH: STARTSWITH,
        OPERATORS.ISTARTSWITH: ISTARTSWITH,
        OPERATORS.ENDSWITH: ENDSWITH,
        OPERATORS.IENDSWITH: IENDSWITH,
    }


class TextFieldFilter(StringFieldFilter):

    def get_widget(self, request):
        return forms.TextInput()


class DateFilter(OperatorsModelFieldFilter):

    suffixes = {
        'day', 'month', 'year'
    }
    operators = {
        OPERATORS.EQ: EQ,
        OPERATORS.NEQ: NEQ,
        OPERATORS.LT: LT,
        OPERATORS.GT: GT,
        OPERATORS.LTE: LTE,
        OPERATORS.GTE: GTE,
        OPERATORS.IN: IN,
    }

    def _clean_integer(self, value):
        try:
            return int(value)
        except ValueError:
            raise FilterValueException(ugettext('Value must be integer'))

    def _clean_datetime(self, value):
        try:
            datetime_value = DEFAULTPARSER.parse(value, dayfirst='-' not in value)
            return make_aware(datetime_value) if datetime_value.tzinfo is None else datetime_value
        except ValueError:
            raise FilterValueException(ugettext('Value must be in format ISO 8601.'))

    def clean_value(self, value, request):
        suffix = self.get_suffix()
        if suffix in self.suffixes:
            return self._clean_integer(value)
        else:
            return self._clean_datetime(value)


class DateTimeFilter(DateFilter):

    suffixes = {
        'day', 'month', 'year', 'hour', 'minute', 'second'
    }


class RelatedFieldFilter(OperatorsModelFieldFilter):

    def get_last_rel_field(self, field):
        if not field.is_relation:
            return field
        else:
            next_field = field.rel.to._meta.get_field(field.rel.field_name)
            return self.get_last_rel_field(next_field)


class ForeignKeyFilter(RelatedFieldFilter):

    operators = {
        OPERATORS.EQ: EQ,
        OPERATORS.NEQ: NEQ,
        OPERATORS.LT: LT,
        OPERATORS.GT: GT,
        OPERATORS.LTE: LTE,
        OPERATORS.GTE: GTE,
        OPERATORS.IN: IN,
    }

    def clean_value(self, value, request):
        try:
            return self.get_last_rel_field(self.field).get_prep_value(value)
        except ValueError:
            raise FilterValueException(ugettext('Object with this PK cannot be found'))


class ManyToManyFieldFilter(RelatedFieldFilter):

    operators = {
        OPERATORS.IN: IN,
        OPERATORS.ALL: ALL,
    }

    def clean_value(self, value, request):
        try:
            return self.get_last_rel_field(
                self.field.rel.to._meta.get_field(self.field.m2m_target_field_name())
            ).get_prep_value(value)
        except ValueError:
            raise FilterValueException(ugettext('Object with this PK cannot be found'))


class ForeignObjectRelFilter(RelatedFieldFilter):

    operators = {
        OPERATORS.IN: IN,
        OPERATORS.ALL: ALL,
    }
    widget = forms.TextInput()

    def clean_value(self, value, request):
        try:
            return self.get_last_rel_field(
                self.field.related_model._meta.get_field(self.field.related_model._meta.pk.name)
            ).get_prep_value(value)
        except ValueError:
            raise FilterValueException(ugettext('Object with this PK cannot be found'))


class SimpleEqualFilter(Filter):

    def _get_filter_prefix(self):
        return self.identifiers[:-2] if self.get_suffix() else self.identifiers[:-1]

    def _update_q_with_prefix(self, q):
        if isinstance(q, Q):
            q.children = [self._update_q_with_prefix(child) for child in q.children]
            return q
        else:
            return ('{}__{}'.format(self._get_filter_prefix(), q[0], q[1]))

    def get_q(self, value, operator, request):
        if operator != OPERATORS.EQ:
            raise OperatorFilterException
        else:
            filter_term = self.get_filter_term(self.clean_value(value, request), request)
            return self._update_q_with_prefix(Q(**filter_term) if isinstance(filter_term, dict) else filter_term)

    def clean_value(self, value, request):
        return value


class SimpleMethodEqualFilter(MethodFilterMixin, SimpleEqualFilter):
    pass


class SimpleModelFieldEqualFilter(ModelFieldFilterMixin, SimpleEqualFilter):
    pass


BooleanField.default_filter = BooleanFieldFilter
TextField.default_filter = TextFieldFilter
CharField.default_filter = StringFieldFilter
IntegerField.default_filter = IntegerFieldFilter
FloatField.default_filter = FloatFieldFilter
DecimalField.default_filter = DecimalFieldFilter
AutoField.default_filter = IntegerFieldFilter
DateField.default_filter = DateFilter
DateTimeField.default_filter = DateTimeFilter
GenericIPAddressField.default_filter = StringFieldFilter
IPAddressField.default_filter = StringFieldFilter
ManyToManyField.default_filter = ManyToManyFieldFilter
ForeignKey.default_filter = ForeignKeyFilter
ForeignObjectRel.default_filter = ForeignObjectRelFilter
SlugField.default_filter = StringFieldFilter
EmailField.default_filter = StringFieldFilter
