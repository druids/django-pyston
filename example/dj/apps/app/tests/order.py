from germanium.tools.trivials import assert_equal
from germanium.tools.http import assert_http_bad_request, build_url
from germanium.tools.rest import assert_valid_JSON_response

from .factories import IssueFactory, UserFactory
from .test_case import PystonTestCase


class OrderTestCase(PystonTestCase):

    def test_order_by_decorator(self):
        [IssueFactory(description=str(i)) for i in range(10)]
        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, order='short_description')))
        assert_equal([v['short_description'] for v in data], [str(i) for i in range(10)])
        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, order='-short_description')))
        assert_equal([v['short_description'] for v in data], [str(i) for i in range(10)][::-1])
        assert_valid_JSON_response(self.get(build_url(self.USER_API_URL, order='solving_issue__short_description')))
        assert_valid_JSON_response(self.get(build_url(self.USER_API_URL, order='-solving_issue__short_description')))
        assert_http_bad_request(self.get(build_url(self.ISSUE_API_URL, order='description')))

    def test_override_extra_order_fields(self):
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, order='created_at')))
        assert_valid_JSON_response(
            self.get(build_url(self.USER_API_URL, order='email,-solving_issue__short_description'))
        )

    def test_issue_can_order_only_with_readable_fields_and_extra_field(self):
        assert_valid_JSON_response(self.get(build_url(self.ISSUE_API_URL, order='solver__created_at')))
        assert_valid_JSON_response(self.get(build_url(self.ISSUE_API_URL, order='created_at')))
        assert_http_bad_request(self.get(build_url(self.ISSUE_API_URL, order='solver__manual_created_date')))

    def test_extra_sorter(self):
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()
        user1.watched_issues.add(*(IssueFactory() for _ in range(2)))
        user3.watched_issues.add(*(IssueFactory() for _ in range(5)))

        users_pks = {user1.pk, user2.pk, user3.pk}

        resp = self.get(build_url(self.USER_API_URL, order='watched_issues_count'))
        assert_valid_JSON_response(resp)
        assert_equal(self.get_pk_list(resp, only_pks=users_pks), [user2.pk, user1.pk, user3.pk])

        resp = self.get(build_url(self.USER_API_URL, order='-watched_issues_count'))
        assert_valid_JSON_response(resp)
        assert_equal(self.get_pk_list(resp, only_pks=users_pks), [user3.pk, user1.pk, user2.pk])
