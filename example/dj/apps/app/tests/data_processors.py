# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import base64

from germanium.rest import RESTTestCase
from germanium.anotations import data_provider

from .test_case import PystonTestCase

from app.models import User, Issue


class DataProcessorsTestCase(PystonTestCase):

    @data_provider('get_users_data')
    def test_create_user_with_file(self, number, data):
        data['contract'] = {
            'content_type': 'text/plain',
            'filename': 'contract.txt',
            'content': base64.b64encode(
                ('Contract of %s code: šří+áýšé' % data['email']).encode('utf-8')
            ).decode('utf-8')
        }
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        data = self.deserialize(resp)
        self.assert_not_equal(data['contract'], None)
        self.assert_in('filename', data['contract'])
        self.assert_in('url', data['contract'])
        self.assert_equal(data['contract']['content_type'], 'text/plain')

    @data_provider('get_users_data')
    def test_create_user_with_file_and_not_defined_content_type(self, number, data):
        data['contract'] = {
            'filename': 'contract.txt',
            'content': base64.b64encode(
                ('Contract of %s code: šří+áýšé' % data['email']).encode('utf-8')
            ).decode('utf-8')
        }
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        data = self.deserialize(resp)
        self.assert_not_equal(data['contract'], None)
        self.assert_in('filename', data['contract'])
        self.assert_in('url', data['contract'])
        self.assert_equal(data['contract']['content_type'], 'text/plain')

    @data_provider('get_users_data')
    def test_error_during_creating_user_with_file_and_not_defined_content_type(self, number, data):
        data['contract'] = {
            'filename': 'contract',
            'content': base64.b64encode(
                ('Contract of %s code: šří+áýšé' % data['email']).encode('utf-8')
            ).decode('utf-8')
        }
        resp = self.post(self.USER_API_URL, data=self.serialize(data))
        self.assert_http_bad_request(resp)

    @data_provider('get_issues_and_users_data')
    def test_atomic_create_issue_with_user_id(self, number, issue_data, user_data):
        resp = self.post(self.USER_API_URL, data=self.serialize(user_data))
        issue_data['created_by'] = self.get_pk(resp)
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(issue_data))
        self.assert_valid_JSON_created_response(resp)

    @data_provider('get_issues_data')
    def test_atomic_create_issue_with_user(self, number, data):
        users_before_count = User.objects.all().count()
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        self.assert_equal(users_before_count + 2, User.objects.all().count())

    @data_provider('get_issues_data')
    def test_atomic_update_issue_with_user(self, number, data):
        users_before_count = User.objects.all().count()
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        self.assert_equal(users_before_count + 2, User.objects.all().count())
        data['created_by'] = self.get_user_data()
        data['created_by']['id'] = self.deserialize(resp)['created_by']['id']
        data['leader'] = self.get_user_data()
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(data))
        self.assert_valid_JSON_created_response(resp)
        self.assert_equal(users_before_count + 3, User.objects.all().count())

    @data_provider('get_issues_and_users_data')
    def test_atomic_set_issue_with_user_reverse(self, number, issue_data, user_data):
        issues_before_count = Issue.objects.all().count()
        user_data['created_issues'] = {'set': (issue_data,)}
        resp = self.post(self.USER_API_URL, data=self.serialize(user_data))
        self.assert_valid_JSON_created_response(resp)
        self.assert_equal(issues_before_count + 1, Issue.objects.all().count())

    @data_provider('get_issues_and_users_data')
    def test_atomic_add_and_delete_issues_with_reverse(self, number, issue_data, user_data):
        issues_before_count = Issue.objects.all().count()

        user_data['created_issues'] = {'add': (self.get_issue_data(), self.get_issue_data(), self.get_issue_data())}
        resp = self.post(self.USER_API_URL, data=self.serialize(user_data))

        self.assert_valid_JSON_created_response(resp)
        self.assert_equal(issues_before_count + 3, Issue.objects.all().count())
        user_pk = self.get_pk(resp)

        user_data['created_issues'] = {'set': (self.get_issue_data(), self.get_issue_data(), self.get_issue_data())}
        resp = self.put('%s%s/' % (self.USER_API_URL, user_pk), data=self.serialize(user_data))
        self.assert_equal(issues_before_count + 3, Issue.objects.all().count())
        self.assert_valid_JSON_response(resp)
        user_data['created_issues'] = {'remove': list(Issue.objects.filter(created_by=user_pk).
                                                      values_list('pk', flat=True))}
        resp = self.put('%s%s/' % (self.USER_API_URL, self.get_pk(resp)), data=self.serialize(user_data))
        self.assert_valid_JSON_response(resp)
        self.assert_equal(issues_before_count, Issue.objects.all().count())

    @data_provider('get_issues_and_users_data')
    def test_atomic_add_delete_and_set_issues_with_errors(self, number, issue_data, user_data):
        user_data['created_issues'] = {'set': (None, "", None, {}, [None])}
        resp = self.post(self.USER_API_URL, data=self.serialize(user_data))
        self.assert_http_bad_request(resp)
        self.assert_in('set', self.deserialize(resp).get('messages', {}).get('errors', {}).get('created_issues', {}))

        user_data['created_issues'] = {'add': (None, "", None, [], {}, {"id": 500}),
                                       'remove': (None, "", None, {}, {"id": 500}, [])}
        resp = self.post(self.USER_API_URL, data=self.serialize(user_data))
        self.assert_http_bad_request(resp)
        self.assert_in('add', self.deserialize(resp).get('messages', {}).get('errors', {}).get('created_issues', {}))
        self.assert_in('remove', self.deserialize(resp).get('messages', {}).get('errors', {}).get('created_issues', {}))

        user_data['created_issues'] = {'add': None, 'remove': None}
        resp = self.post(self.USER_API_URL, data=self.serialize(user_data))
        self.assert_http_bad_request(resp)
        self.assert_in('add', self.deserialize(resp).get('messages', {}).get('errors', {}).get('created_issues', {}))
        self.assert_in('remove', self.deserialize(resp).get('messages', {}).get('errors', {}).get('created_issues', {}))

    @data_provider('get_issues_and_users_data')
    def test_atomic_set_issue_with_watchers(self, number, issue_data, user_data):
        users_before_count = User.objects.all().count()

        issue_data['created_by'] = user_data
        issue_data['watched_by'] = self.get_users_data(flat=True)
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(issue_data))
        self.assert_valid_JSON_created_response(resp)
        self.assert_equal(users_before_count + 12, User.objects.all().count())

        issue_data['leader'] = self.get_user_data()
        issue_data['created_by'] = self.get_user_data()
        issue_data['watched_by'] = {'set': self.get_users_data(flat=True)}

        resp = self.post(self.ISSUE_API_URL, data=self.serialize(issue_data))
        self.assert_valid_JSON_created_response(resp)
        self.assert_equal(users_before_count + 24, User.objects.all().count())

    @data_provider('get_issues_and_users_data')
    def test_atomic_add_and_delete_issue_with_watchers(self, number, issue_data, user_data):
        issue_data['created_by'] = user_data
        issue_data['watched_by'] = {'add': self.get_users_data(flat=True)}
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(issue_data))
        self.assert_valid_JSON_created_response(resp)
        self.assert_equal(len(self.deserialize(resp).get('watched_by')), 10)

        pk = self.get_pk(resp)
        issue_data['created_by'] = self.get_user_data()
        issue_data['leader'] = self.get_user_data()
        issue_data['watched_by'] = {'add': self.get_users_data(flat=True),
                                    'remove': [obj.get('id') for obj in self.deserialize(resp).get('watched_by')][:5]}
        resp = self.put('%s%s/' % (self.ISSUE_API_URL, pk), data=self.serialize(issue_data))
        self.assert_equal(len(self.deserialize(resp).get('watched_by')), 15)

    @data_provider('get_issues_and_users_data')
    def test_atomic_add_delete_and_set_issue_with_watchers_with_errors(self, number, issue_data, user_data):
        issue_data['created_by'] = user_data
        issue_data['watched_by'] = {'add': [None, [], 'invalid_text', {}], 'remove': ['invalid_text', 5, {}]}
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(issue_data))
        self.assert_http_bad_request(resp)
        self.assert_in('add', self.deserialize(resp).get('messages', {}).get('errors').get('watched_by'))
        self.assert_in('remove', self.deserialize(resp).get('messages', {}).get('errors').get('watched_by'))

        issue_data['created_by'] = user_data
        issue_data['watched_by'] = {'set': [None, [], 'invalid_text', {}]}
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(issue_data))
        self.assert_http_bad_request(resp)
        self.assert_in('set', self.deserialize(resp).get('messages', {}).get('errors').get('watched_by'))

        issue_data['created_by'] = user_data
        issue_data['watched_by'] = {'set': ''}
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(issue_data))
        self.assert_http_bad_request(resp)
        self.assert_in('set', self.deserialize(resp).get('messages', {}).get('errors').get('watched_by'))

        issue_data['created_by'] = user_data
        issue_data['watched_by'] = {'set': None}
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(issue_data))
        self.assert_http_bad_request(resp)
        self.assert_in('set', self.deserialize(resp).get('messages', {}).get('errors').get('watched_by'))

        issue_data['created_by'] = user_data
        issue_data['watched_by'] = {'set': {}}
        resp = self.post(self.ISSUE_API_URL, data=self.serialize(issue_data))
        self.assert_http_bad_request(resp)
        self.assert_in('set', self.deserialize(resp).get('messages', {}).get('errors').get('watched_by'))

    @data_provider('get_issues_and_users_data')
    def test_create_issue_via_user_one_to_one(self, number, issue_data, user_data):
        issues_before_count = Issue.objects.all().count()
        issue_data['created_by'] = self.get_user_data()
        user_data['leading_issue'] = issue_data
        resp = self.post(self.USER_API_URL, data=self.serialize(user_data))
        self.assert_valid_JSON_created_response(resp)
        self.assert_equal(issues_before_count + 1, Issue.objects.all().count())

        pk = self.get_pk(resp)
        user_data = {'leading_issue': None}
        resp = self.put('%s%s/' % (self.USER_API_URL, pk), data=self.serialize(user_data))
        self.assert_valid_JSON_response(resp)
        self.assert_equal(issues_before_count, Issue.objects.all().count())

        user_data = {'leading_issue': None}
        resp = self.put('%s%s/' % (self.USER_API_URL, pk), data=self.serialize(user_data))
        self.assert_valid_JSON_response(resp)
        self.assert_equal(issues_before_count, Issue.objects.all().count())

        user_data = {'leading_issue': self.get_issue_data()}
        resp = self.put('%s%s/' % (self.USER_API_URL, pk), data=self.serialize(user_data))
        self.assert_valid_JSON_response(resp)
        self.assert_equal(issues_before_count + 1, Issue.objects.all().count())

    @data_provider('get_issues_and_users_data')
    def test_create_issue_via_user_one_to_one_bad_request(self, number, issue_data, user_data):
        issue_data['created_by'] = self.get_user_data()
        user_data['leading_issue'] = {}
        resp = self.post(self.USER_API_URL, data=self.serialize(user_data))
        self.assert_http_bad_request(resp)
        self.assert_in('leading_issue', self.deserialize(resp).get('messages', {}).get('errors'))

        user_data['leading_issue'] = 'bad data'
        resp = self.post(self.USER_API_URL, data=self.serialize(user_data))
        self.assert_http_bad_request(resp)
        self.assert_in('leading_issue', self.deserialize(resp).get('messages', {}).get('errors'))