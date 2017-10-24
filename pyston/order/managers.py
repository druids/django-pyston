from __future__ import unicode_literals

from django.utils.safestring import mark_safe
from django.utils.translation import ugettext

from pyston.exception import RESTException
from pyston.utils import rfs, LOOKUP_SEP
from pyston.utils.helpers import get_field_or_none, get_method_or_none
from pyston.serializer import get_resource_or_none

from .exceptions import OrderIdentifierError
from .parsers import DefaultOrderParser, OrderParserError
from .utils import DIRECTION


def get_allowed_order_fields_rfs_from_model(model):
    return rfs(model._rest_meta.extra_order_fields).join(rfs(model._rest_meta.order_fields))


class ModelOrderManager(object):
    """
    Order manager is used inside model resource for order response queryset according to input values.
    This is abstract class that provides methods to obtain concrete order strings from resource and model methods
    and fields.
    """

    def _get_order_string_from_method(self, method, identifiers_prefix, identifiers, model, resource, request,
                                      order_fields_rfs):
        """
        :param method: method from which we can get order string.
        :param identifiers_prefix: because order strings are recursive if model relations property contains list of
               identifiers that was used for recursive searching the order string.
        :param identifiers: list of identifiers that conclusively identifies order string.
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
            return self._get_order_string_recursive(
                identifiers_prefix, order_identifiers, model, resource, request, next_order_fields_rfs
            )
        raise OrderIdentifierError

    def _get_order_string_from_resource(self, identifiers_prefix, identifiers, model, resource, request,
                                        order_fields_rfs):
        """
        :param identifiers_prefix: because order strings are recursive if model relations property contains list of
               identifiers that was used for recursive searching the order string.
        :param identifiers: list of identifiers that conclusively identifies order string.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param order_fields_rfs: RFS of fields that is allowed to order.
        :return: db order method string that is obtained from resource object.
        """
        full_identifiers_string = LOOKUP_SEP.join(identifiers)
        resource_method = get_method_or_none(resource, full_identifiers_string)
        if full_identifiers_string in order_fields_rfs and resource_method:
            return self._get_order_string_from_method(resource_method, identifiers_prefix, identifiers, model,
                                                      resource, request, order_fields_rfs)

    def _get_order_string_from_model(self, identifiers_prefix, identifiers, model, resource, request, order_fields_rfs):
        """
        :param identifiers_prefix: because order strings are recursive if model relations property contains list of
               identifiers that was used for recursive searching the order string.
        :param identifiers: list of identifiers that conclusively identifies order string.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param order_fields_rfs: RFS of fields that is allowed to order.
        :return: db order method string that is obtained from model fields or methods.
        """
        current_identifier = identifiers[0]
        identifiers_suffix = identifiers[1:]

        if current_identifier not in order_fields_rfs:
            raise OrderIdentifierError

        model_field = get_field_or_none(model, current_identifier)
        model_method = get_method_or_none(model, current_identifier)

        if model_field and not identifiers_suffix and (not model_field.is_relation or model_field.related_model):
            return LOOKUP_SEP.join(identifiers_prefix + identifiers)
        elif model_field and model_field.is_relation and model_field.related_model:
            next_model = model_field.related_model
            next_resource = get_resource_or_none(request, next_model, getattr(resource, 'resource_typemapper'))
            return self._get_order_string_recursive(
                identifiers_prefix + [identifiers[0]], identifiers[1:],
                next_model, next_resource, request, order_fields_rfs[current_identifier].subfieldset
            )
        elif model_method and not identifiers_suffix:
            return self._get_order_string_from_method(
                model_method, identifiers_prefix, identifiers, model, resource, request, order_fields_rfs
            )

    def _get_order_string_recursive(self, identifiers_prefix, identifiers, model, resource, request,
                                    extra_order_fields_rfs=None):
        """
        :param identifiers_prefix: because order strings are recursive if model relations property contains list of
               identifiers that was used for recursive searching the order string.
        :param identifiers: list of identifiers that conclusively identifies order string.
        :param model: django model class.
        :param resource: resource object.
        :param request: django HTTP request.
        :param extra_order_fields_rfs: RFS of fields that is allowed to order.
        :return: method search resursice order string with order_string_from_model or order_string_from_resource
                 getters.
        """
        extra_order_fields_rfs = rfs() if extra_order_fields_rfs is None else extra_order_fields_rfs
        order_fields_rfs = (
            extra_order_fields_rfs.join(
                resource.get_order_fields_rfs() if resource else get_allowed_order_fields_rfs_from_model(model)
            )
        )

        order_string = (
            self._get_order_string_from_resource(
                identifiers_prefix, identifiers, model, resource, request, order_fields_rfs) or
            self._get_order_string_from_model(
                identifiers_prefix, identifiers, model, resource, request, order_fields_rfs)
        )
        if not order_string:
            raise OrderIdentifierError
        return order_string

    def get_order_string(self, identifiers, resource, request):
        """
        :param identifiers: list of identifiers that conclusively identifies a order string.
        :param resource: resource object.
        :param request: django HTTP request.
        :return: method returns filter string according to input identifiers, resource and request.
        """
        return self._get_order_string_recursive([], identifiers, resource.model, resource, request)


class ParserModelOrderManager(ModelOrderManager):
    """
    Manager that uses parser to parse input order data to the list of order strings.
    """

    parser = None

    def _convert_order_terms(self, parsed_order_terms, resource, request):
        """
        Method that converts order terms to the django query order strings.
        """
        ordering_strings = []
        for ordering_term in parsed_order_terms:
            try:
                ordering_strings.append('{}{}'.format(
                    '-' if ordering_term.direction == DIRECTION.DESC else '',
                    self.get_order_string(ordering_term.identifiers, resource, request)
                ))
            except OrderIdentifierError:
                raise RESTException(
                    mark_safe(ugettext('Invalid identifier of ordering "{}"').format(ordering_term.source))
                )
        return ordering_strings

    def order(self, resource, qs, request):
        try:
            parsed_order_terms = self.parser.parse(request)
            return qs.order_by(
                *self._convert_order_terms(parsed_order_terms, resource, request)
            ) if parsed_order_terms else qs
        except OrderParserError as ex:
            raise RESTException(ex)


class DefaultModelOrderManager(ParserModelOrderManager):
    """
    Default order manager.
    """

    parser = DefaultOrderParser()
