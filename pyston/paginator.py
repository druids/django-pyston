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


def _get_attr(obj, attr):
    if '__' in attr:
        rel_obj, rel_attr = attr.split('__')
        return _get_attr(getattr(obj, rel_obj), rel_attr)
    else:
        return getattr(obj, attr)


class BasePaginator:

    def __init__(self, qs, request):
        self.qs = qs
        self.request = request

    @property
    def page_qs(self):
        raise NotImplementedError

    @property
    def headers(self):
        return {}


class OffsetBasedPaginator(BasePaginator):
    """
    REST paginator for list and querysets
    """

    MAX_OFFSET = pow(2, 63) - 1
    MAX_BASE = 100

    def __init__(self, qs, request):
        super().__init__(qs, request)
        self.base = self._get_base(request)
        self.total = self._get_total()
        self.offset = self._get_offset(request)
        self.next_offset = self._get_next_offset()
        self.prev_offset = self._get_prev_offset()

    def _get_next_offset(self):
        if self.total:
            return self.offset + self.base if self.base and self.offset + self.base < self.total else None
        else:
            if not self.base:
                return None
            next_offset = self.offset + self.base
            return next_offset if self.qs[next_offset:next_offset + 1].exists() else None

    def _get_prev_offset(self):
        return None if self.offset == 0 or not self.base else max(self.offset - self.base, 0)

    def _get_total(self):
        if isinstance(self.qs, QuerySet):
            return self.qs.count()
        else:
            return len(self.qs)

    def _get_offset(self, request):
        offset = request._rest_context.get('offset', '0')
        if offset.isdigit():
            offset_int = int(offset)
            if offset_int > self.MAX_OFFSET:
                raise RESTException(ugettext('Offset must be lower or equal to {}').format(self.MAX_OFFSET))
            else:
                return offset_int
        else:
            raise RESTException(ugettext('Offset must be natural number'))

    def _get_base(self, request):
        base = request._rest_context.get('base')
        if not base:
            return None
        elif base.isdigit():
            base_int = int(base)
            if base_int > self.MAX_BASE:
                raise RESTException(ugettext('Base must lower or equal to {}').format(self.MAX_BASE))
            else:
                return base_int
        else:
            raise RESTException(ugettext('Base must be natural number or empty'))

    @property
    def page_qs(self):
        if self.base is not None:
            return self.qs[self.offset:(self.offset + self.base)]
        else:
            return self.qs[self.offset:]

    @property
    def headers(self):
        return {
            k: v for k, v in {
                'X-Total': self.total,
                'X-Next-Offset': self.next_offset,
                'X-Prev-Offset': self.prev_offset,
            }.items() if v is not None
        }


class OffsetBasedPaginatorWithoutTotal(OffsetBasedPaginator):

    def _get_total(self):
        return None


class CursorBasedPaginator(BasePaginator):

    MAX_BASE = 100

    def __init__(self, qs, request):
        super().__init__(qs, request)
        self.base = self._get_base(request)
        self.cursor = self._get_cursor(request)

        self._pk_field_name = get_last_parent_pk_field_name(self.qs.model)
        self._ordering = self._get_ordering(request, qs)
        self._next_cursor = None

    def _get_base(self, request):
        base = request._rest_context.get('base')
        if not base:
            return None
        elif base.isdigit():
            base_int = int(base)
            if base_int > self.MAX_BASE:
                raise RESTException(ugettext('Base must lower or equal to {}').format(self.MAX_BIG_INT))
            else:
                return base_int
        else:
            raise RESTException(ugettext('Base must be natural number or empty'))

    def _get_cursor(self, request):
        return request._rest_context.get('cursor')

    def _get_ordering(self, request, qs):
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
            ordering.append(self._pk_field_name)

        return ordering

    def _get_position_from_instance(self, instance):
        if isinstance(instance, dict):
            attr = instance[self._pk_field_name]
        else:
            attr = getattr(instance, self._pk_field_name)
        return str(attr)

    def get_page(self, qs):
        if self.base:
            results = list(qs[:self.base + 1])
            page = list(results[:self.base])

            self._next_cursor = self._get_position_from_instance(page[-1]) if len(results) > len(page) else None

            return ModelIterableIteratorHelper(page, qs.model)
        else:
            return qs

    def _get_field_name(self, order_lookup):
        return order_lookup[1:] if order_lookup.startswith('-') else order_lookup

    def _get_page_filter_kwargs(self, current_row):
        ordering = list(self._ordering)

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


    @property
    def page_qs(self):
        qs = self.qs.order_by(*self._ordering)

        if self.cursor:
            current_row = get_object_or_none(qs, pk=self.cursor)
            if current_row:
                qs = qs.filter(self._get_page_filter_kwargs(current_row))
            else:
                raise RESTException(RESTValidationError(
                    ugettext('Cursor object was not found'),
                    code=ERROR_CODE.PAGINATION)
                )
        return self.get_page(qs)

    @property
    def headers(self):
        return {
            k: v for k, v in {
                'X-Next-Cursor': self._next_cursor,
            }.items() if v is not None
        }