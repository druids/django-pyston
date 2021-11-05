from django.test.utils import override_settings

from germanium.decorators import data_consumer
from germanium.tools.trivials import assert_in, assert_equal, assert_true, assert_is_not_none
from germanium.tools.http import (assert_http_bad_request, assert_http_not_found, assert_http_method_not_allowed,
                                  assert_http_accepted, build_url)
from germanium.tools.rest import assert_valid_JSON_created_response, assert_valid_JSON_response

from .factories import UserFactory, IssueFactory
from .test_case import PystonTestCase

from app.dynamo.models import Comment


class DynamodbTestCase(PystonTestCase):

    COMMENT_API_URL = '/api/issue/{}/Dynamo-comment/'

    @classmethod
    def setUpClass(cls):
        Comment.create_table()
        for i in range(10):
            comment = Comment(
                user_id=str(i),
                issue_id=str(i % 3),
                content=f'test message {i}',
                is_public=bool(i % 2),
                priority=i
            )
            comment.save()

    @classmethod
    def tearDownClass(cls):
        Comment.delete_table()

    def test_get_Dynamo_comments_should_return_right_data(self):
        resp = self.get(self.COMMENT_API_URL.format(0))
        assert_valid_JSON_response(resp)
        assert_equal(len(resp.json()), 4)
        for i, data in enumerate(resp.json()):
            assert_equal(data['priority'], i * 3)
            assert_equal(data['user_id'], str(i * 3))
            assert_equal(data['is_public'], bool(i % 2))
            assert_equal(data['content'], f'test message {i * 3}')
            assert_equal(data['issue_id'], str(0))

        resp = self.get(self.COMMENT_API_URL.format(1))
        assert_equal(len(resp.json()), 3)

        resp = self.get(self.COMMENT_API_URL.format(2))
        assert_equal(len(resp.json()), 3)

    def test_get_one_Dynamo_comment_should_return_right_data(self):
        resp = self.get(f'{self.COMMENT_API_URL.format(0)}3/')
        assert_valid_JSON_response(resp)
        data = resp.json()
        assert_equal(data['priority'], 3)
        assert_equal(data['user_id'], '3')
        assert_equal(data['is_public'], True)
        assert_equal(data['content'], f'test message 3')
        assert_equal(data['issue_id'], '0')

    def test_get_Dynamo_comments_should_be_sorted(self):
        resp = self.get(build_url(self.COMMENT_API_URL.format(0), order='user_id'))
        assert_equal([v['user_id'] for v in resp.json()], ['0', '3', '6', '9'])
        resp = self.get(build_url(self.COMMENT_API_URL.format(0), order='-user_id'))
        assert_equal([v['user_id'] for v in resp.json()], ['9', '6', '3', '0'])
        assert_http_bad_request(self.get(build_url(self.COMMENT_API_URL.format(0), order='id')))

    def test_get_Dynamo_comments_should_be_filtered(self):
        resp = self.get(build_url(self.COMMENT_API_URL.format(0), filter='user_id=0'))
        assert_equal(len(resp.json()), 1)
        resp = self.get(build_url(self.COMMENT_API_URL.format(0), filter='user_id=10'))
        assert_equal(len(resp.json()), 0)
        assert_http_bad_request(self.get(build_url(self.COMMENT_API_URL.format(0), filter='invalid=5')))

    def test_get_Dynamo__comments_should_paginated(self):
        headers = {'HTTP_X_BASE': '3'}
        resp = self.get(self.COMMENT_API_URL.format(0), headers=headers)
        assert_true('x-next-cursor' in resp)
        assert_equal([v['user_id'] for v in resp.json()], ['0', '3', '6'])
        headers['HTTP_X_CURSOR'] = resp['x-next-cursor']
        resp = self.get(self.COMMENT_API_URL.format(0), headers=headers)
        assert_equal([v['user_id'] for v in resp.json()], ['9'])

