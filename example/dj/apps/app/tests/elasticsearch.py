from django.test.utils import override_settings

from germanium.decorators import data_consumer
from germanium.tools.trivials import assert_in, assert_equal, assert_true, assert_is_not_none
from germanium.tools.http import (assert_http_bad_request, assert_http_not_found, assert_http_method_not_allowed,
                                  assert_http_accepted, build_url)
from germanium.tools.rest import assert_valid_JSON_created_response, assert_valid_JSON_response

from .factories import UserFactory, IssueFactory
from .test_case import PystonTestCase

from app.elasticsearch.models import Comment


class ElasticsearchTestCase(PystonTestCase):

    COMMENT_API_URL = '/api/elasticsearch-comment/'

    @classmethod
    def setUpClass(cls):
        for i in range(10):
            comment = Comment(
                user_id=str(i),
                content=f'test message {i}',
                is_public=bool(i % 2),
                priority=i
            )
            comment.meta.id = i
            comment.save()
        Comment._index.refresh()

    @classmethod
    def tearDownClass(cls):
        Comment._index.delete()

    def test_get_elasticsearch_comments_should_return_right_data(self):
        resp = self.get(self.COMMENT_API_URL)
        assert_valid_JSON_response(resp)
        assert_equal(len(resp.json()), 10)
        for i, data in enumerate(resp.json()):
            assert_equal(data['priority'], i)
            assert_equal(data['user_id'], str(i))
            assert_equal(data['is_public'], bool(i % 2))
            assert_equal(data['content'], f'test message {i}')
            assert_equal(data['id'], str(i))

    def test_get_one_elasticsearch_comment_should_return_right_data(self):
        for i in range(10):
            resp = self.get(f'{self.COMMENT_API_URL}{i}/')
            assert_valid_JSON_response(resp)
            data = resp.json()
            assert_equal(data['priority'], i)
            assert_equal(data['user_id'], str(i))
            assert_equal(data['is_public'], bool(i % 2))
            assert_equal(data['content'], f'test message {i}')
            assert_is_not_none(data['id'])

    def test_get_elasticsearch_comments_should_be_sorted(self):
        resp = self.get(build_url(self.COMMENT_API_URL, order='priority'))
        assert_equal([v['priority'] for v in resp.json()], [i for i in range(10)])
        resp = self.get(build_url(self.COMMENT_API_URL, order='-priority'))
        assert_equal([v['priority'] for v in resp.json()], [i for i in range(10)][::-1])

        resp = self.get(build_url(self.COMMENT_API_URL, order='is_public'))
        assert_equal(resp.json()[0]['is_public'], False)
        resp = self.get(build_url(self.COMMENT_API_URL, order='-is_public'))
        assert_equal(resp.json()[0]['is_public'], True)

        resp = self.get(build_url(self.COMMENT_API_URL, order='user_id'))
        assert_equal([v['user_id'] for v in resp.json()], [str(i) for i in range(10)])
        resp = self.get(build_url(self.COMMENT_API_URL, order='-user_id'))
        assert_equal([v['user_id'] for v in resp.json()], [str(i) for i in range(10)][::-1])

        assert_http_bad_request(self.get(build_url(self.COMMENT_API_URL, order='content')))
        assert_http_bad_request(self.get(build_url(self.COMMENT_API_URL, order='id')))
        assert_http_bad_request(self.get(build_url(self.COMMENT_API_URL, order='invalid')))

    def test_get_elasticsearch_comments_should_be_filtered(self):
        resp = self.get(build_url(self.COMMENT_API_URL, filter='user_id=5'))
        assert_equal(len(resp.json()), 1)
        resp = self.get(build_url(self.COMMENT_API_URL, filter='content icontains "test message"'))
        assert_equal(len(resp.json()), 10)
        resp = self.get(build_url(self.COMMENT_API_URL, filter='content icontains "test message 1"'))
        assert_equal(len(resp.json()), 1)
        resp = self.get(build_url(self.COMMENT_API_URL, filter='is_public=1'))
        assert_equal(len(resp.json()), 5)
        assert_http_bad_request(self.get(build_url(self.COMMENT_API_URL.format(0), filter='invalid=5')))

    def test_get_elasticsearch_comments_should_paginated(self):
        headers = {'HTTP_X_OFFSET': '0', 'HTTP_X_BASE': '5'}
        resp = self.get(self.COMMENT_API_URL, headers=headers)
        assert_equal(len(self.deserialize(resp)), min(int(resp['x-total']), 5))

        headers = {'HTTP_X_OFFSET': '2', 'HTTP_X_BASE': '5'}
        resp = self.get(self.COMMENT_API_URL, headers=headers)
        assert_equal(len(self.deserialize(resp)), min(max(int(resp['x-total']) - 2, 0), 5))

        headers = {'HTTP_X_OFFSET': '2', 'HTTP_X_BASE': '-5'}
        resp = self.get(self.COMMENT_API_URL, headers=headers)
        assert_http_bad_request(resp)

        headers = {'HTTP_X_OFFSET': '-2', 'HTTP_X_BASE': '5'}
        resp = self.get(self.COMMENT_API_URL, headers=headers)
        assert_http_bad_request(resp)

        headers = {'HTTP_X_OFFSET': 'error', 'HTTP_X_BASE': 'error'}
        resp = self.get(self.COMMENT_API_URL, headers=headers)
        assert_http_bad_request(resp)
