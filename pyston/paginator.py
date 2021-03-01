from functools import reduce
from operator import or_

from chamber.shortcuts import get_object_or_none

from django.utils.translation import ugettext
from django.db.models.query import QuerySet
from django.db.models import Q
from django.db.models.expressions import OrderBy
from django.utils.translation import ugettext

from .forms import RESTValidationError
from .exception import RESTException
from .utils.compatibility import get_last_parent_pk_field_name
from .utils.helpers import ModelIterableIteratorHelper
from .response import HeadersResponse


def _get_attr(obj, attr):
    if '__' in attr:
        rel_obj, rel_attr = attr.split('__')
        return _get_attr(getattr(obj, rel_obj), rel_attr)
    else:
        return getattr(obj, attr)


class BasePaginator:

    def get_response(self, qs, request):
        raise NotImplementedError


class OffsetBasedPaginator(BasePaginator):
    """
    REST paginator for list and querysets
    """

    def __init__(self, max_offset=pow(2, 63) - 1, max_base=100, default_base=20):
        self.max_offset = max_offset
        self.max_base = max_base
        self.default_base = default_base

    def get_response(self, qs, request):
        base = self._get_base(qs, request)
        total = self._get_total(qs, request)
        offset = self._get_offset(qs, request)
        qs = qs[offset:(offset + base + 1)]
        next_offset = self._get_next_offset(qs, offset, base, total)
        prev_offset = self._get_prev_offset(qs, offset, base, total)

        return HeadersResponse(
            ModelIterableIteratorHelper(qs[:base], qs.model),
            self.get_headers(total, next_offset, prev_offset)
        )

    def _get_offset(self, qs, request):
        offset = request._rest_context.get('offset', '0')
        if offset.isdigit():
            offset_int = int(offset)
            if offset_int > self.max_offset:
                raise RESTException(ugettext('Offset must be lower or equal to {}').format(self.max_offset))
            else:
                return offset_int
        else:
            raise RESTException(ugettext('Offset must be natural number'))

    def _get_base(self, qs, request):
        base = request._rest_context.get('base')
        if not base:
            return self.default_base
        elif base.isdigit():
            base_int = int(base)
            if base_int > self.max_base:
                raise RESTException(ugettext('Base must lower or equal to {}').format(self.max_base))
            else:
                return base_int
        else:
            raise RESTException(ugettext('Base must be natural number or empty'))

    def _get_total(self, qs, request):
        if isinstance(qs, QuerySet):
            return qs.count()
        else:
            return len(qs)

    def _get_next_offset(self, qs, offset, base, total):
        if total:
            return offset + base if base and offset + base < total else None
        else:
            return offset + base if len(qs) > base else None

    def _get_prev_offset(self, qs, offset, base, total):
        return None if offset == 0 or not base else max(offset - base, 0)

    def get_headers(self, total, next_offset, prev_offset):
        return {
            k: v for k, v in {
                'X-Total': total,
                'X-Next-Offset': next_offset,
                'X-Prev-Offset': prev_offset,
            }.items() if v is not None
        }


class OffsetBasedPaginatorWithoutTotal(OffsetBasedPaginator):

    def _get_total(self, qs, request):
        return None


class CursorBasedModelIterableIteratorHelper(ModelIterableIteratorHelper):

    def __init__(self, iterable, model, next):
        super().__init__(iterable, model)
        self.next = next


class CursorBasedPaginator(BasePaginator):

    def __init__(self, max_base=100, default_base=20):
        self.max_base = max_base
        self.default_base = default_base

    def get_response(self, qs, request):
        base = self._get_base(request)
        cursor = self._get_cursor(request)

        ordering = self._get_ordering(request, qs)

        cursor_based_model_iterable = self._get_paged_qs(qs, ordering, cursor, base)

        return HeadersResponse(
            cursor_based_model_iterable,
            self.get_headers(cursor_based_model_iterable.next)
        )

    def _get_page_filter_kwargs(self, current_row, ordering):
        ordering = list(ordering)

        args_or = []
        while ordering:
            base_order_field_name = ordering.pop()
            is_reverse = base_order_field_name.startswith('-')
            base_order_field_name = self._get_field_name(base_order_field_name)
            base_order_filtered_value = _get_attr(current_row, base_order_field_name)
            if base_order_filtered_value is None:
                if is_reverse:
                    filter_lookup = Q(**{'{}__isnull'.format(base_order_field_name): False})
                else:
                    # skip this filter
                    continue
            else:
                if is_reverse:
                    filter_lookup = Q(
                        **{'{}__lt'.format(base_order_field_name): base_order_filtered_value}
                    )
                else:
                    filter_lookup = Q(
                        **{'{}__gt'.format(base_order_field_name): base_order_filtered_value}
                    ) | Q(
                        **{'{}__isnull'.format(base_order_field_name): True}
                    )

            args_or.append(
                Q(
                    filter_lookup,
                    Q(**{
                        self._get_field_name(order): _get_attr(
                            current_row, self._get_field_name(order)
                        ) for order in ordering
                    })
                )
            )
        return reduce(or_, args_or)

    def _get_page(self, qs, base):
        results = list(qs[:base + 1])
        page = list(results[:base])
        next_cursor = self._get_position_from_instance(page[-1]) if len(results) > len(page) else None
        return CursorBasedModelIterableIteratorHelper(page, qs.model, next=next_cursor)

    @property
    def _get_paged_qs(self, qs, ordering, cursor, base):
        qs = qs.order_by(*ordering)

        if cursor:
            current_row = get_object_or_none(qs, pk=cursor)
            if current_row:
                qs = qs.filter(self._get_page_filter_kwargs(current_row))
            else:
                raise RESTException(RESTValidationError(
                    ugettext('Cursor object was not found'),
                    code=ERROR_CODE.PAGINATION)
                )
        return self._get_page(qs, base)

    def _get_base(self, request):
        base = request._rest_context.get('base')
        if not base:
            return self.default_base
        elif base.isdigit():
            base_int = int(base)
            if base_int > self.max_base:
                raise RESTException(ugettext('Base must lower or equal to {}').format(self.max_base))
            else:
                return base_int
        else:
            raise RESTException(ugettext('Base must be natural number or empty'))

    def _get_cursor(self, request):
        return request._rest_context.get('cursor')

    def _get_ordering(self, request, qs):
        pk_field_name = get_last_parent_pk_field_name(qs.model)
        query_ordering = list(qs.query.order_by) or list(qs.model._meta.ordering)

        ordering = []
        for order_lookup in query_ordering:
            if isinstance(order_lookup, OrderBy):
                ordering.append(
                    '-' + order_lookup.expression.name if order_lookup.descending else order_lookup.expression.name
                )
            else:
                ordering.append(order_lookup)

        if self._pk_field_name not in ordering:
            ordering.append(pk_field_name)

        return ordering

    def _get_position_from_instance(self, instance):
        pk_field_name = get_last_parent_pk_field_name(instance.__class__)
        if isinstance(instance, dict):
            attr = instance[pk_field_name]
        else:
            attr = getattr(instance, pk_field_name)
        return str(attr)

    def _get_field_name(self, order_lookup):
        return order_lookup[1:] if order_lookup.startswith('-') else order_lookup

    def get_headers(self, next_cursor):
        return {
            k: v for k, v in {
                'X-Next-Cursor': next_cursor,
            }.items() if v is not None
        }