from django.utils.safestring import mark_safe
from django.utils.translation import ugettext

from pyston.exception import RestException
from pyston.utils import rfs, LOOKUP_SEP
from pyston.utils.helpers import get_field_or_none, get_method_or_none
from pyston.serializer import get_resource_or_none

from .exceptions import OrderIdentifierError
from .parsers import DefaultOrderParser, OrderParserError
from .django_sorters import DjangoSorter


def get_allowed_order_fields_rfs_from_model(model):
    return rfs(model._rest_meta.extra_order_fields).join(rfs(model._rest_meta.order_fields))


class BaseModelOrderManager:
    """
    Order manager is used inside object resource for order response queryset according to input values.
    This is abstract class that provides methods to obtain concrete order strings from resource and model methods
    and fields.
    """

    def _get_real_field_name(self, resource, field_name):
        return resource.renamed_fields.get(field_name, field_name) if resource else field_name

    def _get_sorter_from_method(self, method, identifiers_prefix, identifiers, direction, model, resource, request,
                                order_fields_rfs):
        """
        :param method: method from which we can get order string.
        :param identifiers_prefix: because order strings are recursive if model relations property contains list of
               identifiers that was used for recursive searching the order string.
        :param identifiers: list of identifiers that conclusively identifies order string.
        :param direction: direction of ordering ASC or DESC.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param order_fields_rfs: RFS of fields that is allowed to order.
        :return: db order method string that is obtained from method.
        """
        if hasattr(method, 'order_by'):
            # If method has order_by attribute order string is being searched according to this value.
            order_identifiers = method.order_by.split(LOOKUP_SEP)
            # Because method must be inside allowed order fields RFS, we must add value order_by of the method
            # to the next RFS.
            next_order_fields_rfs = rfs(order_identifiers)
            return self._get_sorter_recursive(
                identifiers_prefix, order_identifiers, direction, model, resource, request, next_order_fields_rfs
            )
        if not identifiers_prefix and hasattr(method, 'sorter'):
            return method.sorter(identifiers_prefix + identifiers, direction)
        raise OrderIdentifierError

    def _get_sorter_from_resource(self, identifiers_prefix, identifiers, direction, model, resource, request,
                                  order_fields_rfs):
        """
        :param identifiers_prefix: because order strings are recursive if model relations property contains list of
               identifiers that was used for recursive searching the order string.
        :param identifiers: list of identifiers that conclusively identifies order string.
        :param direction: direction of ordering ASC or DESC.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param order_fields_rfs: RFS of fields that is allowed to order.
        :return: db order method string that is obtained from resource object.
        """
        full_identifiers_string = self._get_real_field_name(resource, LOOKUP_SEP.join(identifiers))

        resource_method = resource.get_method_returning_field_value(full_identifiers_string) if resource else None
        if full_identifiers_string in order_fields_rfs and resource_method:
            return self._get_sorter_from_method(resource_method, identifiers_prefix, identifiers, direction, model,
                                                resource, request, order_fields_rfs)

    def _get_sorter_from_model(self, identifiers_prefix, identifiers, direction, model, resource, request,
                               order_fields_rfs):
        return None

    def _get_order_fields_rfs(self, model, resource):
        return resource.get_order_fields_rfs() if resource else rfs()

    def _get_sorter_recursive(self, identifiers_prefix, identifiers, direction, model, resource, request,
                              extra_order_fields_rfs=None):
        """
        :param identifiers_prefix: because order strings are recursive if model relations property contains list of
               identifiers that was used for recursive searching the order string.
        :param identifiers: list of identifiers that conclusively identifies order string.
        :param direction: direction of ordering ASC or DESC.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param extra_order_fields_rfs: RFS of fields that is allowed to order.
        :return: method search resursice order string with order_string_from_model or order_string_from_resource
                 getters.
        """
        extra_order_fields_rfs = rfs() if extra_order_fields_rfs is None else extra_order_fields_rfs
        order_fields_rfs = extra_order_fields_rfs.join(self._get_order_fields_rfs(model, resource))
        order_string = (
            self._get_sorter_from_resource(
                identifiers_prefix, identifiers, direction, model, resource, request, order_fields_rfs) or
            self._get_sorter_from_model(
                identifiers_prefix, identifiers, direction, model, resource, request, order_fields_rfs)
        )
        if not order_string:
            raise OrderIdentifierError
        return order_string

    def get_sorter(self, identifiers, direction, resource, request):
        """
        :param identifiers: list of identifiers that conclusively identifies a order string.
        :param direction: direction of ordering ASC or DESC.
        :param resource: resource object.
        :param request: django HTTP request.
        :return: method returns filter string according to input identifiers, resource and request.
        """
        return self._get_sorter_recursive([], identifiers, direction, resource.model, resource, request)


class BaseDjangoOrderManager(BaseModelOrderManager):
    """
    Order manager is used inside model resource for order response queryset according to input values.
    This is abstract class that provides methods to obtain concrete order strings from resource and model methods
    and fields.
    """

    def _get_order_fields_rfs(self, model, resource):
        return resource.get_order_fields_rfs() if resource else get_allowed_order_fields_rfs_from_model(model)

    def _get_sorter_from_model(self, identifiers_prefix, identifiers, direction, model, resource, request,
                               order_fields_rfs):
        """
        :param identifiers_prefix: because order strings are recursive if model relations property contains list of
               identifiers that was used for recursive searching the order string.
        :param identifiers: list of identifiers that conclusively identifies order string.
        :param direction: direction of ordering ASC or DESC.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param order_fields_rfs: RFS of fields that is allowed to order.
        :return: db order method string that is obtained from model fields or methods.
        """
        current_identifier = self._get_real_field_name(resource, identifiers[0])
        identifiers_suffix = identifiers[1:]

        if current_identifier not in order_fields_rfs:
            raise OrderIdentifierError

        model_field = get_field_or_none(model, current_identifier)
        model_method = get_method_or_none(model, current_identifier)

        if model_field and not identifiers_suffix and (not model_field.is_relation or model_field.related_model):
            return DjangoSorter(identifiers_prefix + identifiers, direction)
        elif model_field and model_field.is_relation and model_field.related_model:
            next_model = model_field.related_model
            next_resource = get_resource_or_none(request, next_model, getattr(resource, 'resource_typemapper', None))
            return self._get_sorter_recursive(
                identifiers_prefix + [identifiers[0]], identifiers[1:], direction,
                next_model, next_resource, request, order_fields_rfs[current_identifier].subfieldset
            )
        elif model_method and not identifiers_suffix:
            return self._get_sorter_from_method(
                model_method, identifiers_prefix, identifiers, direction, model, resource, request, order_fields_rfs
            )


class BaseParserModelOrderManager(BaseModelOrderManager):

    parsers = [DefaultOrderParser()]

    def _get_sorters(self, parsed_order_terms, resource, request):
        """
        Converts order terms to sorter classes
        """
        sorters = []
        for ordering_term in parsed_order_terms:
            try:
                sorters.append(self.get_sorter(ordering_term.identifiers, ordering_term.direction, resource, request))
            except OrderIdentifierError:
                raise RestException(
                    mark_safe(ugettext('Invalid identifier of ordering "{}"').format(ordering_term.source))
                )
        return sorters

    def _convert_order_terms(self, sorters):
        """
        Converts sorters to the django query order strings.
        """
        return [sorter.get_order_term() for sorter in sorters]

    def _update_queryset(self, qs, sorters):
        """
        Update queryset for extra sorter class (it is used for annotations before ordering)
        """
        for sorter in sorters:
            qs = sorter.update_queryset(qs)
        return qs

    def _sort_queryset(self, qs, terms):
        raise NotImplementedError

    def _sort_with_parser(self, parser, resource, qs, request):
        try:
            parsed_order_terms = parser.parse(request)
            sorters = self._get_sorters(parsed_order_terms or (), resource, request)
            qs = self._update_queryset(qs, sorters)
            return self._sort_queryset(qs, self._convert_order_terms(sorters)) if sorters else qs
        except OrderParserError as ex:
            raise RestException(ex)

    def sort(self, resource, qs, request):
        for parser in self.parsers:
            qs = self._sort_with_parser(parser, resource, qs, request)
        return qs


class DjangoOrderManager(BaseParserModelOrderManager, BaseDjangoOrderManager):
    """
    Manager that uses parser to parse input order data to the list of order strings.
    """

    def _sort_queryset(self, qs, terms):
        return qs.order_by(*terms)
