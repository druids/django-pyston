from decimal import Decimal, InvalidOperation

from django.core.validators import validate_ipv4_address, validate_ipv46_address
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import make_aware

from dateutil.parser import DEFAULTPARSER

from pyston.utils import LOOKUP_SEP

from .exceptions import FilterValueError, OperatorFilterError
from .utils import OperatorSlug


NONE_LABEL = _('(None)')


class OperatorQuery:
    """
    OperatorQuery is used for specific type of filters that allows more different ways how to filter queryset
    data according to input operator between identifier and value.
    """

    def get_q(self, value, request):
        """
        Method must be implemented inside descendant and should return django db Q object that will be used for purpose
        of filtering queryset.
        """
        raise NotImplementedError


class Filter:
    """
    Filters purpose is return Q object that is used for filtering data that resource returns.
    Filter can be joined to the field, method or resource.
    """

    suffixes = {}
    choices = None
    allowed_operators = {}

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

    def clean_value(self, value, operator_slug, request):
        """
        Method that cleans input value to the filter specific format.
        """
        return value

    def get_full_filter_key(self):
        return LOOKUP_SEP.join(self.full_identifiers)

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

    def get_q(self, value, operator_slug, request):
        operator_obj = self.get_operator_obj(operator_slug)
        return operator_obj.get_q(self, value, operator_slug, request)


class MethodFilter(Filter):
    """
    Abstract parent for all method filters.
    """

    def __init__(self, identifiers_prefix, identifiers, identifiers_suffix, model, method=None):
        assert method, 'Method is required'
        super().__init__(identifiers_prefix, identifiers, identifiers_suffix, model, method=method)


class ModelFieldFilter(Filter):
    """
    Abstract parent for all model field filters.
    """

    def __init__(self, identifiers_prefix, identifiers, identifiers_suffix, model, field=None):
        assert field, 'Field is required'
        super().__init__(identifiers_prefix, identifiers, identifiers_suffix, model, field=field)


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
            return super().clean_value(value, operator_slug, request)


class IntegerFilterMixin:
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


class FloatFilterMixin:

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        try:
            return float(value)
        except (ValueError, TypeError):
            raise FilterValueError(ugettext('Value must be float'))


class DecimalFilterMixin:

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        try:
            return Decimal(value)
        except InvalidOperation:
            raise FilterValueError(ugettext('Value must be decimal'))


class IPAddressFilterMixin:

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        elif operator_slug not in {OperatorSlug.CONTAINS, OperatorSlug.EXACT,
                                   OperatorSlug.STARTSWITH, OperatorSlug.ENDSWITH}:
            try:
                validate_ipv4_address(value)
            except ValidationError:
                raise FilterValueError(ugettext('Value must be in format IPv4.'))
        return value


class GenericIPAddressFilterMixin:

    def clean_value(self, value, operator_slug, request):
        if value is None:
            return value
        elif operator_slug not in {OperatorSlug.CONTAINS, OperatorSlug.EXACT,
                                   OperatorSlug.STARTSWITH, OperatorSlug.ENDSWITH}:
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
        elif operator_slug == OperatorSlug.CONTAINS:
            return self._clean_datetime_to_parts(value)
        elif value is None:
            return value
        else:
            return self._clean_datetime(value)
