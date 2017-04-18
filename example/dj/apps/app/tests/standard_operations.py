from six.moves.urllib.parse import urlencode

from germanium.anotations import data_provider

from .factories import UserFactory, IssueFactory
from .test_case import PystonTestCase


class StandardOperationsTestCase(PystonTestCase):

    ACCEPT_TYPES = (
        'application/json',
        'text/xml',
        'text/csv',
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )

    @data_provider('get_users_data')
    def test_create_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        pk = self.deserialize(resp)['id']
        resp = self.get(self.USER_API_URL)
        self.assert_equal(len(self.deserialize(resp)), 1)
        self.assert_valid_JSON_response(self.get('%s%s/' % (self.USER_API_URL, pk)))

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

        self.assert_valid_JSON_response(self.put('{}{}/'.format(self.USER_API_URL, pk), data=self.serialize({})))

        self.assert_http_bad_request(
            self.put('{}{}/'.format(self.USER_API_URL, pk), data=self.serialize({'email': 'invalid_email'}))
        )

        self.assert_http_not_found(self.put('{}{}/'.format(self.USER_API_URL, 0), data=self.serialize({})))


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
        self.assert_equal(len(self.deserialize(resp)), 1)

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
    def test_read_user_detailed_fields_set_with_metaclass(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        pk = self.get_pk(resp)
        resp = self.get('%s%s/' % (self.USER_API_URL, pk),)
        output_data = self.deserialize(resp)
        self.assert_equal(set(output_data.keys()), {'id', 'createdAt', '_obj_name', 'email', 'contract',
                                                    'solvingIssue', 'firstName', 'lastName', 'watchedIssues'})

    @data_provider('get_users_data')
    def test_read_user_general_fields_set_with_metaclass(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        resp = self.get(self.USER_API_URL)
        output_data = self.deserialize(resp)
        self.assert_equal(set(output_data[0].keys()), {'id', '_obj_name', 'email', 'firstName', 'lastName',
                                                       'watchedIssues'})

    @data_provider('get_users_data')
    def test_read_user_extra_fields_set_with_metaclass(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        headers = {'HTTP_X_FIELDS': 'is_superuser'}
        resp = self.get(self.USER_API_URL, headers=headers)

        output_data = self.deserialize(resp)
        self.assert_equal(set(output_data[0].keys()), {'isSuperuser'})

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
        self.assert_equal(int(resp['X-Total']), 1)
        for item_data in self.deserialize(resp):
            self.assert_equal(set(item_data.keys()), {'email', 'id'})

    @data_provider('get_users_data')
    def test_read_extra_field_header_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        headers = {'HTTP_X_FIELDS': 'email'}
        resp = self.get(self.USER_API_URL, headers=headers)
        for item_data in self.deserialize(resp):
            self.assert_equal(set(item_data.keys()), {'email'})

    @data_provider('get_users_data')
    def test_read_headers_paginator_user(self, number, data):
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
    def test_read_querystring_paginator_user(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)

        querystring = {'_offset': '0', '_base': '5'}
        resp = self.get('%s?%s' % (self.USER_API_URL, urlencode(querystring)))
        self.assert_equal(len(self.deserialize(resp)), min(int(resp['x-total']), 5))

        querystring = {'_offset': '2', '_base': '5'}
        resp = self.get('%s?%s' % (self.USER_API_URL, urlencode(querystring)))
        self.assert_equal(len(self.deserialize(resp)), min(max(int(resp['x-total']) - 2, 0), 5))

        querystring = {'_offset': '2', '_base': '-5'}
        resp = self.get('%s?%s' % (self.USER_API_URL, urlencode(querystring)))
        self.assert_http_bad_request(resp)

        querystring = {'_offset': '-2', '_base': '5'}
        resp = self.get('%s?%s' % (self.USER_API_URL, urlencode(querystring)))
        self.assert_http_bad_request(resp)

        querystring = {'_offset': 'error', '_base': 'error'}
        resp = self.get('%s?%s' % (self.USER_API_URL, urlencode(querystring)))
        self.assert_http_bad_request(resp)

    @data_provider('get_users_data')
    def test_read_user_with_more_headers_accept_types(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        pk = self.get_pk(resp)
        for accept_type in self.ACCEPT_TYPES:
            resp = self.get(self.USER_API_URL, headers={'HTTP_ACCEPT': accept_type})
            self.assert_in(accept_type, resp['Content-Type'])
            resp = self.get('%s%s/' % (self.USER_API_URL, pk), headers={'HTTP_ACCEPT': accept_type})
            self.assert_true(accept_type in resp['Content-Type'])
            resp = self.get('%s1050/' % self.USER_API_URL, headers={'HTTP_ACCEPT': accept_type})
            self.assert_true(accept_type in resp['Content-Type'])
            self.assert_http_not_found(resp)

    @data_provider('get_users_data')
    def test_read_user_with_more_querystring_accept_types(self, number, data):
        user = UserFactory()
        [issue.watched_by.add(user) for issue in (IssueFactory() for _ in range(10))]

        for accept_type in self.ACCEPT_TYPES:
            resp = self.get('%s?_accept=%s' % (self.USER_API_URL, accept_type))
            self.assert_in(accept_type, resp['Content-Type'])
            resp = self.get('%s%s/?_accept=%s' % (self.USER_API_URL, user.pk, accept_type),
                            headers={'HTTP_ACCEPT': accept_type})
            self.assert_true(accept_type in resp['Content-Type'])
            resp = self.get('%s1050/?_accept=%s' % (self.USER_API_URL, accept_type),
                            headers={'HTTP_ACCEPT': accept_type})
            self.assert_true(accept_type in resp['Content-Type'])
            self.assert_http_not_found(resp)

    @data_provider('get_users_data')
    def test_head_requests(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        pk = self.get_pk(resp)

        resp = self.head(self.USER_API_URL)
        self.assert_equal(resp.content.decode('utf-8'), '')

        resp = self.head('%s%s/' % (self.USER_API_URL, pk))
        self.assert_equal(resp.content.decode('utf-8'), '')

    @data_provider('get_users_data')
    def test_options_requests(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        pk = self.get_pk(resp)

        resp = self.options(self.USER_API_URL)
        self.assert_equal(resp.content.decode('utf-8'), '')
        self.assert_equal(set(resp['Allow'].split(',')), {'OPTIONS', 'HEAD', 'POST', 'GET'})

        resp = self.options('%s%s/' % (self.USER_API_URL, pk))
        self.assert_equal(resp.content.decode('utf-8'), '')
        self.assert_equal(set(resp['Allow'].split(',')), {'PUT', 'HEAD', 'GET', 'OPTIONS', 'DELETE'})

    @data_provider('get_users_data')
    def test_not_allowed_requests(self, number, data):
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        pk = self.get_pk(resp)

        resp = self.post('%s%s/' % (self.USER_API_URL, pk), data=self.serialize(data))
        self.assert_http_method_not_allowed(resp)

        resp = self.delete(self.USER_API_URL)
        self.assert_http_method_not_allowed(resp)

        resp = self.put(self.USER_API_URL, data=self.serialize(data))
        self.assert_http_method_not_allowed(resp)

    def test_not_valid_string_input_data(self):
        resp = self.post(self.USER_API_URL, data=self.serialize('string_data'))
        self.assert_http_bad_request(resp)

    def test_not_valid_input_media_type(self):
        resp = self.post(self.USER_API_URL, data=self.serialize('string_data'), content_type='text/xml')
        return self.assertEqual(resp.status_code, 415)

    def test_camel_snake_case_transformation(self):
        data = {'barBaz': 'testing data'}
        resp = self.post(self.TEST_CC_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        self.assert_equals(data, self.deserialize(resp))

    def test_camel_snake_case_nested(self):
        resp = self.get(self.TEST_CC_API_URL)
        self.assert_valid_JSON_response(resp)

        data = {
            'fooBar': 'foo bar',
            'connected': {'fizBaz': 'test object property content'}
        }
        self.assert_equals(data, self.deserialize(resp))
