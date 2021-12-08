from six.moves.urllib.parse import urlencode

from django.test import TestCase
from django.test.utils import override_settings

from germanium.test_cases.rest import RestTestCase
from germanium.tools.trivials import assert_true, assert_false, assert_equal
from germanium.decorators import data_consumer

from pyston.resource import (ACCESS_CONTROL_ALLOW_ORIGIN, ACCESS_CONTROL_EXPOSE_HEADERS,
                             ACCESS_CONTROL_ALLOW_CREDENTIALS, ACCESS_CONTROL_ALLOW_HEADERS,
                             ACCESS_CONTROL_ALLOW_METHODS, ACCESS_CONTROL_MAX_AGE)

from .test_case import PystonTestCase


FOO_DOMAIN = 'http://foo.pyston.net'
BAR_DOMAIN = 'http://bar.pyston.net'


class CorsTestCase(PystonTestCase):

    @override_settings(PYSTON_CORS=False)
    @data_consumer('get_users_data')
    def test_with_turned_off_cors_headers_is_not_included(self, number, data):
        resp = self.options(self.USER_API_URL)
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_ORIGIN))
        assert_false(resp.has_header(ACCESS_CONTROL_EXPOSE_HEADERS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_CREDENTIALS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_HEADERS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_METHODS))
        assert_false(resp.has_header(ACCESS_CONTROL_MAX_AGE))

        resp = self.get(self.USER_API_URL)
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_ORIGIN))
        assert_false(resp.has_header(ACCESS_CONTROL_EXPOSE_HEADERS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_CREDENTIALS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_HEADERS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_METHODS))
        assert_false(resp.has_header(ACCESS_CONTROL_MAX_AGE))

    @override_settings(PYSTON_CORS=True, PYSTON_CORS_WHITELIST=[FOO_DOMAIN[7:]])
    @data_consumer('get_users_data')
    def test_option_with_turned_on_cors_headers_is_included_with_valid_origin(self, number, data):
        resp = self.options(self.USER_API_URL)
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_ORIGIN))
        assert_true(resp.has_header(ACCESS_CONTROL_EXPOSE_HEADERS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_CREDENTIALS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_HEADERS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_METHODS))
        assert_true(resp.has_header(ACCESS_CONTROL_MAX_AGE))

        resp = self.options(self.USER_API_URL, headers={'HTTP_ORIGIN': FOO_DOMAIN})
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_ORIGIN))
        assert_true(resp.has_header(ACCESS_CONTROL_EXPOSE_HEADERS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_CREDENTIALS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_HEADERS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_METHODS))
        assert_true(resp.has_header(ACCESS_CONTROL_MAX_AGE))

        resp = self.options(self.USER_API_URL, headers={'HTTP_ORIGIN': BAR_DOMAIN})
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_ORIGIN))
        assert_true(resp.has_header(ACCESS_CONTROL_EXPOSE_HEADERS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_CREDENTIALS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_HEADERS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_METHODS))

    @override_settings(PYSTON_CORS=True, PYSTON_CORS_WHITELIST=[FOO_DOMAIN[7:]])
    @data_consumer('get_users_data')
    def test_with_turned_on_cors_headers_is_included_with_valid_origin(self, number, data):
        resp = self.options(self.USER_API_URL, headers={'HTTP_ORIGIN': FOO_DOMAIN})
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_ORIGIN))
        assert_true(resp.has_header(ACCESS_CONTROL_EXPOSE_HEADERS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_CREDENTIALS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_HEADERS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_METHODS))
        assert_true(resp.has_header(ACCESS_CONTROL_MAX_AGE))

        resp = self.get(self.USER_API_URL, headers={'HTTP_ORIGIN': FOO_DOMAIN})
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_ORIGIN))
        assert_true(resp.has_header(ACCESS_CONTROL_EXPOSE_HEADERS))
        assert_true(resp.has_header(ACCESS_CONTROL_ALLOW_CREDENTIALS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_HEADERS))
        assert_false(resp.has_header(ACCESS_CONTROL_ALLOW_METHODS))
        assert_true(resp.has_header(ACCESS_CONTROL_MAX_AGE))

    @override_settings(PYSTON_CORS=True, PYSTON_CORS_MAX_AGE=60 * 10)
    @data_consumer('get_users_data')
    def test_cors_max_age(self, number, data):
        resp = self.options(self.USER_API_URL)
        assert_equal(resp[ACCESS_CONTROL_MAX_AGE], '600')

    @override_settings(PYSTON_CORS=True, PYSTON_CORS_ALLOW_CREDENTIALS=True)
    @data_consumer('get_users_data')
    def test_cors_allow_credentials_true(self, number, data):
        resp = self.options(self.USER_API_URL)
        assert_equal(resp[ACCESS_CONTROL_ALLOW_CREDENTIALS], 'true')

    @override_settings(PYSTON_CORS=True, PYSTON_CORS_ALLOW_CREDENTIALS=False)
    @data_consumer('get_users_data')
    def test_cors_allow_credentials_false(self, number, data):
        resp = self.options(self.USER_API_URL)
        assert_equal(resp[ACCESS_CONTROL_ALLOW_CREDENTIALS], 'false')

    @override_settings(PYSTON_CORS=True, PYSTON_CORS_ALLOW_CREDENTIALS=False, PYSTON_CORS_WHITELIST=[FOO_DOMAIN[7:]])
    @data_consumer('get_users_data')
    def test_cors_allow_headers(self, number, data):
        resp = self.options(self.USER_API_URL, headers={'HTTP_ORIGIN': FOO_DOMAIN})
        assert_equal(resp[ACCESS_CONTROL_ALLOW_HEADERS],
                          ', '.join(('X-Base', 'X-Offset', 'X-Fields', 'Origin', 'Content-Type', 'Accept')))

        resp = self.options(self.USER_API_URL, headers={'HTTP_ORIGIN': BAR_DOMAIN})
        assert_equal(resp[ACCESS_CONTROL_ALLOW_HEADERS],
                          ', '.join(('X-Base', 'X-Offset', 'X-Fields', 'Origin', 'Content-Type', 'Accept')))

        resp = self.options(self.USER_API_URL)
        assert_false(ACCESS_CONTROL_ALLOW_HEADERS in resp)

    @override_settings(PYSTON_CORS=True, PYSTON_CORS_ALLOW_CREDENTIALS=False)
    @data_consumer('get_users_data')
    def test_cors_allow_exposed_headers(self, number, data):
        resp = self.options(self.USER_API_URL)
        assert_equal(resp[ACCESS_CONTROL_EXPOSE_HEADERS],
                          ', '.join(('X-Total', 'X-Serialization-Format-Options', 'X-Fields-Options')))

    @override_settings(PYSTON_CORS=True, PYSTON_CORS_ALLOW_CREDENTIALS=False)
    @data_consumer('get_users_data')
    def test_cors_allow_methods(self, number, data):
        resp = self.options(self.USER_API_URL, headers={'HTTP_ORIGIN': FOO_DOMAIN})
        assert_equal(set(resp[ACCESS_CONTROL_ALLOW_METHODS].split(', ')), {'OPTIONS'})

        resp = self.options(self.USER_API_URL, headers={'HTTP_ORIGIN': FOO_DOMAIN,
                                                        'HTTP_ACCESS_CONTROL_REQUEST_METHOD': 'GET'})
        assert_equal(set(resp[ACCESS_CONTROL_ALLOW_METHODS].split(', ')), {'GET'})

        resp = self.options(self.USER_API_URL, headers={'HTTP_ORIGIN': BAR_DOMAIN})
        assert_equal(set(resp[ACCESS_CONTROL_ALLOW_METHODS].split(', ')), {'OPTIONS'})

        resp = self.options(self.USER_API_URL, headers={'HTTP_ORIGIN': BAR_DOMAIN,
                                                        'HTTP_ACCESS_CONTROL_REQUEST_METHOD': 'POST'})
        assert_equal(set(resp[ACCESS_CONTROL_ALLOW_METHODS].split(', ')), {'POST'})

        resp = self.options(self.USER_API_URL)
        assert_false(ACCESS_CONTROL_ALLOW_METHODS in resp)
