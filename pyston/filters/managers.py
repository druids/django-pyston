from django.db.models import Q
from django.core.exceptions import FieldDoesNotExist
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext

from pyston.exception import RestException
from pyston.utils import rfs, LOOKUP_SEP
from pyston.utils.helpers import get_field_or_none, get_method_or_none
from pyston.serializer import get_resource_or_none

from .exceptions import FilterValueError, OperatorFilterError, FilterIdentifierError
from .utils import LogicalOperatorSlug
from .parser import QueryStringFilterParser, DefaultFilterParser, FilterParserError
from .django_filters import get_default_field_filter_class


def get_allowed_filter_fields_rfs_from_model(model):
    return rfs(model._rest_meta.extra_filter_fields).join(rfs(model._rest_meta.filter_fields))


class BaseModelFilterManager:
    """
    Filter manager is used inside object resource for composing filters with purpose to restrict output data according
    to input values.
    This is abstract class that provides methods to obtain concrete filters from resource and model methods and fields.
    """

    def _get_method_filter(self, method, identifiers_prefix, identifiers, identifiers_suffix, model, resource, request,
                           filters_fields_rfs):
        """
        :param method: method from which we can get filter.
        :param identifiers_prefix: because filters are recursive if model relations property contains list of
               identifiers that was used for recursive searching the filter.
        :param identifiers: list of identifiers that conclusively identifies the filter.
        :param identifiers_suffix: list of suffixes that can be used for more specific filters.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param filters_fields_rfs: RFS of fields that is allowed to filter.
        :return: method returns filter object that is obtained from method.
        """
        if hasattr(method, 'filter_by'):
            # If method has filter_by attribute filter is being searched according to this value.
            filter_by_identifiers = method.filter_by.split(LOOKUP_SEP)
            next_identifiers = filter_by_identifiers + identifiers_suffix
            # Because method must be inside allowed filter fields RFS, we must add value filter_by of the method
            # to the next RFS.
            next_filters_fields_rfs = rfs(filter_by_identifiers)
            return self._get_filter_recursive(
                identifiers_prefix, next_identifiers, model, resource, request, next_filters_fields_rfs
            )
        suffix = LOOKUP_SEP.join(identifiers_suffix)
        if not hasattr(method, 'filter') or (suffix and suffix not in method.filter.get_suffixes()):
            raise FilterIdentifierError
        return method.filter(identifiers_prefix, identifiers, identifiers_suffix, model, method=method)

    def _get_real_field_name(self, resource, field_name):
        return resource.renamed_fields.get(field_name, field_name) if resource else field_name

    def _get_resource_filter(self, identifiers_prefix, identifiers, model, resource, request, filters_fields_rfs):
        """
        :param identifiers_prefix: because filters are recursive if model relations property contains list of
               identifiers that was used for recursive searching the filter.
        :param identifiers: list of identifiers that conclusively identifies the filter.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param filters_fields_rfs: RFS of fields that is allowed to filter.
        :return: method returns filter that is obtained from resource and its methods.
        """
        # Filter is obtained from resource filters dict
        for i in range(1, len(identifiers) + 1):
            # Because resource filters can contains filter key with __ we must try all combinations with suffixes
            current_identifiers = identifiers[:i]
            identifiers_string = self._get_real_field_name(resource, LOOKUP_SEP.join(current_identifiers))
            identifiers_suffix = identifiers[i:]
            suffix_string = LOOKUP_SEP.join(identifiers_suffix)
            if (resource and identifiers_string in resource.filters and
                    (not suffix_string or suffix_string in resource.filters[identifiers_string].get_suffixes())):
                return resource.filters[identifiers_string](
                    identifiers_prefix, current_identifiers, identifiers_suffix, model
                )

        # Filter is obtained from resource methods
        current_identifier = self._get_real_field_name(resource, identifiers[0])
        resource_method = resource.get_method_returning_field_value(current_identifier) if resource else None
        if current_identifier in filters_fields_rfs and resource_method:
            return self._get_method_filter(
                resource_method, identifiers_prefix, [current_identifier], identifiers[1:], model, resource, request,
                filters_fields_rfs
            )

        return None

    def _get_model_filter(self, identifiers_prefix, identifiers, model, resource, request, filters_fields_rfs):
        """
        :param identifiers_prefix: because filters are recursive if model relations property contains list of
               identifiers that was used for recursive searching the filter.
        :param identifiers: list of identifiers that conclusively identifies the filter.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param filters_fields_rfs: RFS of fields that is allowed to filter.
        :return: method returns filter from model fields or methods
        """
        return None

    def _get_filters_fields_rfs(self, model, resource):
        return resource.get_filter_fields_rfs() if resource else rfs()

    def _get_filter_recursive(self, identifiers_prefix, identifiers, model, resource, request,
                              extra_filter_fields_rfs=None):
        """
        :param identifiers_prefix: because filters are recursive if model relations property contains list of
               identifiers that was used for recursive searching the filter.
        :param identifiers: list of identifiers that conclusively identifies the filter.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param extra_filter_fields_rfs: RFS of fields that is allowed to filter.
        :return: method search recursive filter with resource_filter and model_filter getters.
        """
        if not identifiers:
            return None

        extra_filter_fields_rfs = rfs() if extra_filter_fields_rfs is None else extra_filter_fields_rfs
        filters_fields_rfs = extra_filter_fields_rfs.join(self._get_filters_fields_rfs(model, resource))

        filter_obj = (
            self._get_resource_filter(
                identifiers_prefix, identifiers, model, resource, request, filters_fields_rfs
            )
            or self._get_model_filter(
                identifiers_prefix, identifiers, model, resource, request, filters_fields_rfs
            )
        )
        if not filter_obj:
            raise FilterIdentifierError
        return filter_obj

    def get_filter(self, identifiers, resource, request):
        """
        :param identifiers: list of identifiers that conclusively identifies a filter.
        :param resource: resource object.
        :param request: django HTTP request.
        :return: method returns filter object according to input identifiers, resource and request.
        """
        return self._get_filter_recursive([], identifiers, resource.model, resource, request)

    def filter(self, resource, qs, request):
        """
        :param resource: resource object.
        :param qs: model queryset that will be filtered.
        :param request: django HTTP request.
        :return: methods should return filtered queryset.
        """
        raise NotImplementedError


class BaseDjangoFilterManager(BaseModelFilterManager):
    """
    Filter manager is used inside model resource for composing filters with purpose to restrict output data according
    to input values.
    This is abstract class that provides methods to obtain concrete filters from resource and model methods and fields.
    """

    model_field_filters = {}

    def _get_default_model_field_filter_class(self, model_field):
        model_field_filter = getattr(model_field, 'filter', None)
        if model_field_filter:
            return model_field_filter

        for field_class, filter_class in list(self.model_field_filters.items())[::-1]:
            if isinstance(model_field, field_class):
                return filter_class

        return get_default_field_filter_class(model_field)

    def _get_model_filter(self, identifiers_prefix, identifiers, model, resource, request, filters_fields_rfs):
        """
        :param identifiers_prefix: because filters are recursive if model relations property contains list of
               identifiers that was used for recursive searching the filter.
        :param identifiers: list of identifiers that conclusively identifies the filter.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param filters_fields_rfs: RFS of fields that is allowed to filter.
        :return: method returns filter from model fields or methods
        """
        current_identifier = self._get_real_field_name(resource, identifiers[0])
        identifiers_suffix = identifiers[1:]

        if current_identifier not in filters_fields_rfs:
            return None

        suffix = LOOKUP_SEP.join(identifiers_suffix)

        model_field = get_field_or_none(model, current_identifier)
        model_method = get_method_or_none(model, current_identifier)
        model_filter_filter = self._get_default_model_field_filter_class(model_field) if model_field else None

        if model_filter_filter and (not suffix or suffix in model_filter_filter.get_suffixes()):
            return model_filter_filter(
                identifiers_prefix, [current_identifier], identifiers_suffix, model, field=model_field
            )
        elif model_field and model_field.is_relation and model_field.related_model:
            # recursive search for filter via related model fields
            next_model = model_field.related_model
            next_resource = get_resource_or_none(request, next_model, getattr(resource, 'resource_typemapper', None))
            return self._get_filter_recursive(
                identifiers_prefix + [identifiers[0]], identifiers[1:], next_model, next_resource, request,
                filters_fields_rfs[current_identifier].subfieldset
            )
        elif model_method:
            return self._get_method_filter(
                model_method, identifiers_prefix, [current_identifier], identifiers_suffix,
                model, resource, request, filters_fields_rfs
            )
        else:
            return None

    def _get_filters_fields_rfs(self, model, resource):
        return resource.get_filter_fields_rfs() if resource else get_allowed_filter_fields_rfs_from_model(model)


def get_flat_lookups(q):
    if isinstance(q, Q):
        result = []
        for child in q.children:
            result += get_flat_lookups(child)
        return result
    else:
        return [q[0]]


def is_required_distinct_for_lookup(model, lookup, fail_first=False):
    if '__' in lookup:
        curr_lookup, next_lookup = lookup.split('__', 1)
    else:
        curr_lookup, next_lookup = lookup, None
    try:
        field = model._meta.get_field(curr_lookup)
        if not field.is_relation:
            return False
        elif field.many_to_many or field.one_to_many:
            # m2m or o2m relations can cause duplications
            return True
        elif not next_lookup:
            return False
        else:
            return is_required_distinct_for_lookup(field.related_model, next_lookup, True)
    except FieldDoesNotExist:
        # For annotations is distinct automatically required
        return fail_first


class BaseParserModelFilterManager(BaseModelFilterManager):

    parsers = [DefaultFilterParser(), QueryStringFilterParser()]

    def _logical_conditions_and(self, condition_a, condition_b):
        raise RestException(ugettext('More filter terms combination are not supported'))

    def _logical_conditions_or(self, condition_a, condition_b):
        raise RestException(ugettext('More filter terms combination are not supported'))

    def _logical_conditions_negation(self, condition):
        raise RestException(ugettext('Filter term negation are not supported'))

    def _convert_logical_conditions(self, condition, resource, request):
        """
        Method that recursive converts condition tree to the django models Q objects.
        """
        if condition.is_composed and condition.operator_slug == LogicalOperatorSlug.NOT:
            return self._logical_conditions_negation(
                self._convert_logical_conditions(condition.condition_right, resource, request)
            )
        elif condition.is_composed and condition.operator_slug == LogicalOperatorSlug.AND:
            return self._logical_conditions_and(
                self._convert_logical_conditions(condition.condition_left, resource, request),
                self._convert_logical_conditions(condition.condition_right, resource, request)
            )
        elif condition.is_composed and condition.operator_slug == LogicalOperatorSlug.OR:
            return self._logical_conditions_or(
                self._convert_logical_conditions(condition.condition_left, resource, request),
                self._convert_logical_conditions(condition.condition_right, resource, request)
            )
        else:
            try:
                return self.get_filter(condition.identifiers, resource, request).get_q(
                    condition.value, condition.operator_slug, request
                )
            except FilterIdentifierError:
                raise RestException(
                    mark_safe(ugettext('Invalid identifier of condition "{}"').format(condition.source))
                )
            except FilterValueError as ex:
                raise RestException(
                    mark_safe(ugettext('Invalid value of condition "{}". {}').format(condition.source, ex))
                )
            except OperatorFilterError:
                raise RestException(
                    mark_safe(ugettext('Invalid operator of condition "{}"').format(condition.source))
                )

    def _is_required_distinct(self, qs, q):
        for lookup in get_flat_lookups(q):
            if is_required_distinct_for_lookup(qs.model, lookup):
                return True
        return False

    def _filter_queryset(self, qs, q):
        raise NotImplementedError

    def _filter_with_parser(self, parser, resource, qs, request):
        try:
            parsed_conditions = parser.parse(request)
            if parsed_conditions:
                return self._filter_queryset(qs, self._convert_logical_conditions(parsed_conditions, resource, request))
            else:
                return qs
        except FilterParserError as ex:
            raise RestException(ex)

    def filter(self, resource, qs, request):
        for parser in self.parsers:
            qs = self._filter_with_parser(parser, resource, qs, request)
        return qs


class DjangoFilterManager(BaseParserModelFilterManager, BaseDjangoFilterManager):
    """
    Manager that uses parser to parse input filter data to the logical conditions tree.
    """

    def _logical_conditions_and(self, condition_a, condition_b):
        return Q(condition_a, condition_b)

    def _logical_conditions_or(self, condition_a, condition_b):
        return Q(condition_a | condition_b)

    def _logical_conditions_negation(self, condition):
        return ~Q(condition)

    def _is_required_distinct(self, qs, q):
        for lookup in get_flat_lookups(q):
            if is_required_distinct_for_lookup(qs.model, lookup):
                return True
        return False

    def _filter_queryset(self, qs, q):
        if self._is_required_distinct(qs, q):
            return qs.filter(pk__in=qs.filter(q).values('pk'))
        else:
            return qs.filter(q)
