from germanium.rest import RESTTestCase
from germanium.anotations import data_provider

from .test_case import PistonTestCase


class StandardOperationsTestCase(PistonTestCase):

    @data_provider('get_users_data')
    def test_create_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        resp = self.get(self.USER_API_URL)
        self.assert_equal(len(self.deserialize(resp)), number + 1)

    @data_provider('get_users_data')
    def test_create_error_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize({}))
        self.assert_http_bad_request(resp)

        resp = self.post(self.USER_API_URL, data=self.serialize({'email': 'invalid_email'}))
        self.assert_http_bad_request(resp)

    @data_provider('get_users_data')
    def test_update_error_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        pk = self.get_pk(resp)

        resp = self.put('%s%s/' % (self.USER_API_URL, pk), data=self.serialize({}))
        self.assert_valid_JSON_response(resp)

        resp = self.put('%s%s/' % (self.USER_API_URL, pk), data=self.serialize({'email': 'invalid_email'}))
        self.assert_http_bad_request(resp)

    @data_provider('get_users_data')
    def test_update_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        pk = self.get_pk(resp)
        data['email'] = 'updated_%s' % data['email']
        resp = self.put('%s%s/' % (self.USER_API_URL, pk), data=self.serialize(data))
        self.assert_valid_JSON_response(resp)
        self.assert_equal(self.deserialize(resp).get('email'), data['email'])

        resp = self.get(self.USER_API_URL)
        self.assert_equal(len(self.deserialize(resp)), number + 1)

    @data_provider('get_users_data')
    def test_delete_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        pk = self.get_pk(resp)
        resp = self.delete('%s%s/' % (self.USER_API_URL, pk))
        self.assert_http_accepted(resp)

        resp = self.get(self.USER_API_URL)
        self.assert_equal(len(self.deserialize(resp)), 0)

        resp = self.delete('%s%s/' % (self.USER_API_URL, pk))
        self.assert_http_not_found(resp)

    @data_provider('get_users_data')
    def test_read_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        pk = self.get_pk(resp)
        resp = self.get('%s%s/' % (self.USER_API_URL, pk),)
        output_data = self.deserialize(resp)
        self.assert_equal(output_data.get('email'), data.get('email'))
        self.assert_equal(output_data.get('_obj_name'), 'user: %s' % data.get('email'))
        self.assert_equal(output_data.get('id'), pk)

    @data_provider('get_users_data')
    def test_read_field_header_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        pk = self.get_pk(resp)
        headers = {'HTTP_X_FIELDS': 'email,id'}
        resp = self.get('%s%s/' % (self.USER_API_URL, pk), headers=headers)
        output_data = self.deserialize(resp)
        self.assert_equal(set(output_data.keys()), {'email', 'id'})

        resp = self.get(self.USER_API_URL, headers=headers)
        self.assert_equal(resp['X-Total'], str(number + 1))
        for item_data in self.deserialize(resp):
            self.assert_equal(set(item_data.keys()), {'email', 'id'})

    @data_provider('get_users_data')
    def test_read_extra_field_header_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        headers = {'HTTP_X_EXTRA_FIELDS': 'email'}
        resp = self.get(self.USER_API_URL, headers=headers)
        for item_data in self.deserialize(resp):
            self.assert_equal(set(item_data.keys()), {'email', 'id', '_obj_name'})

    @data_provider('get_users_data')
    def test_read_paginator_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        headers = {'HTTP_X_OFFSET': '0', 'HTTP_X_BASE': '5'}
        resp = self.get(self.USER_API_URL, headers=headers)
        self.assert_equal(len(self.deserialize(resp)), min(int(resp['x-total']), 5))

        headers = {'HTTP_X_OFFSET': '2', 'HTTP_X_BASE': '5'}
        resp = self.get(self.USER_API_URL, headers=headers)
        self.assert_equal(len(self.deserialize(resp)), min(max(int(resp['x-total']) - 2, 0), 5))

        headers = {'HTTP_X_OFFSET': '2', 'HTTP_X_BASE': '-5'}
        resp = self.get(self.USER_API_URL, headers=headers)
        self.assert_http_bad_request(resp)

        headers = {'HTTP_X_OFFSET': '-2', 'HTTP_X_BASE': '5'}
        resp = self.get(self.USER_API_URL, headers=headers)
        self.assert_http_bad_request(resp)

        headers = {'HTTP_X_OFFSET': 'error', 'HTTP_X_BASE': 'error'}
        resp = self.get(self.USER_API_URL, headers=headers)
        self.assert_http_bad_request(resp)

    @data_provider('get_users_data')
    def test_read_user_with_more_accept_types(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        pk = self.get_pk(resp)
        for accept_type in ('application/json', 'text/xml', 'application/x-yaml',
                            'application/python-pickle', 'text/csv'):

            resp = self.get(self.USER_API_URL, headers={'HTTP_ACCEPT': accept_type})
            self.assert_in(accept_type, resp['Content-Type'])
            resp = self.get('%s%s/' % (self.USER_API_URL, pk), headers={'HTTP_ACCEPT': accept_type})
            self.assert_true(accept_type in resp['Content-Type'])
            resp = self.get('%s1050/' % self.USER_API_URL, headers={'HTTP_ACCEPT': accept_type})
            self.assert_true(accept_type in resp['Content-Type'])
            self.assert_http_not_found(resp)

    @data_provider('get_users_data')
    def test_head_requests(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        pk = self.get_pk(resp)

        resp = self.head(self.USER_API_URL)
        self.assert_equal(resp.content, '')

        resp = self.head('%s%s/' % (self.USER_API_URL, pk))
        self.assert_equal(resp.content, '')

    @data_provider('get_users_data')
    def test_options_requests(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        pk = self.get_pk(resp)

        resp = self.options(self.USER_API_URL)
        self.assert_equal(resp.content, '')
        self.assert_equal(set(resp['Allowed'].split(',')), {'OPTIONS', 'HEAD', 'POST', 'GET'})

        resp = self.options('%s%s/' % (self.USER_API_URL, pk))
        self.assert_equal(resp.content, '')
        self.assert_equal(set(resp['Allowed'].split(',')), {'PUT', 'HEAD', 'GET', 'OPTIONS', 'DELETE'})

    @data_provider('get_users_data')
    def test_not_allowed_requests(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        pk = self.get_pk(resp)

        resp = self.post('%s%s/' % (self.USER_API_URL, pk), data=self.serialize(data))
        self.assert_http_unauthorized(resp)

        resp = self.delete(self.USER_API_URL)
        self.assert_http_unauthorized(resp)

        resp = self.put(self.USER_API_URL, data=self.serialize(data))
        self.assert_http_unauthorized(resp)

