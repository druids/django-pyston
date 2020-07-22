from django.utils.translation import ugettext
from django.db.models.query import QuerySet

from .exception import RESTException


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


class BaseOffsetPaginator(BasePaginator):
    """
    REST paginator for list and querysets
    """

    MAX_BIG_INT = pow(2, 63) - 1

    def __init__(self, qs, request):
        super().__init__(qs, request)
        self.base = self._get_base(request)
        self.total = self._get_total()
        self.offset = self._get_offset(request)
        self.next_offset = self._get_next_offset()
        self.prev_offset = self._get_prev_offset()

    def _get_next_offset(self):
        return self.offset + self.base if self.base and self.offset + self.base < self.total else None

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
            if offset_int > self.MAX_BIG_INT:
                raise RESTException(ugettext('Offset must be lower or equal to {}').format(self.MAX_BIG_INT))
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
            if base_int > self.MAX_BIG_INT:
                raise RESTException(ugettext('Base must lower or equal to {}').format(self.MAX_BIG_INT))
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


class BaseOffsetPaginatorWithoutTotal(BaseOffsetPaginator):

    def _get_total(self):
        return None

    def _get_next_offset(self):
        if not self.base:
            return None
        next_offset = self.offset + self.base
        return next_offset if self.qs[next_offset:next_offset + 1].exists() else None
