from germanium.rest import RESTTestCase
from germanium.anotations import data_provider

from .test_case import PistonTestCase


class ExtraResourceTestCase(PistonTestCase):

    def test_not_supported_message_for_put_post_and_delete(self):
        resp = self.put(self.EXTRA_API_URL, data=self.serialize({}))
        self.assert_http_method_not_allowed(resp)

        resp = self.post(self.EXTRA_API_URL, data=self.serialize({}))
        self.assert_http_method_not_allowed(resp)

        resp = self.delete(self.EXTRA_API_URL)
        self.assert_http_method_not_allowed(resp)

    def test_should_return_data_for_get(self):
        resp = self.get(self.EXTRA_API_URL)
        self.assert_valid_JSON_response(resp)
