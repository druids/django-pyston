import base64
import json

from django.utils.translation import ugettext

from pyston.exception import RestException
from pyston.paginator import BasePaginator
from pyston.response import HeadersResponse


class DynamoCursorBasedPaginator(BasePaginator):

    def __init__(self, default_base=20, max_base=100):
        self.default_base = default_base
        self.max_base = max_base

    def get_response(self, qs, request):
        base = self._get_base(request)
        cursor = self._get_cursor(request)

        if cursor is not None:
            qs = qs.set_last_evaluated_key(cursor)
        qs = qs.set_limit(base)

        return HeadersResponse(
            qs, self.get_headers(self.get_next_cursor(qs))
        )

    def _get_base(self, request):
        base = request._rest_context.get('base')
        if not base:
            return self.default_base
        elif base.isdigit():
            base_int = int(base)
            if base_int > self.max_base:
                raise RestException(ugettext('Base must lower or equal to {}').format(self.max_base))
            else:
                return base_int
        else:
            raise RestException(ugettext('Base must be natural number or empty'))

    def _get_cursor(self, request):
        cursor = request._rest_context.get('cursor')
        if cursor:
            try:
                cursor = base64.b64decode(
                    cursor.encode('ascii')
                ).decode('ascii')
                return json.loads(cursor)
            except json.JSONDecodeError:
                raise RestException(ugettext('Invalid next cursor value'))
        else:
            return None

    def get_next_cursor(self, qs):
        return base64.b64encode(
            json.dumps(qs.next_key).encode('ascii')
        ).decode('ascii') if qs.next_key else None

    def get_headers(self, next_cursor):
        return {
            k: v for k, v in {
                'X-Next-Cursor': next_cursor,
            }.items() if v is not None
        }
