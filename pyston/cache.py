from django.core.cache import cache


class DefaultRESTCache:
    """
    Cache for improve REST efficiency, works only for GET method
    """

    def _get_cache(self):
        return cache

    def _get_key(self, request):
        return request.get_full_path()

    def cache_response(self, request, response):
        rm = request.method.upper()
        if rm == 'GET':
            self._cache_response(request, response)

    def _cache_response(self, request, response):
        self._get_cache().set(self._get_key(request), response)

    def get_response(self, request):
        rm = request.method.upper()
        if rm == 'GET':
            return self._get_response(request)

    def _get_response(self, request):
        return self._get_cache().get(self._get_key(request))
