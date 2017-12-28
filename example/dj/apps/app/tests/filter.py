from datetime import datetime

from germanium.tools.trivials import assert_equal
from germanium.tools.http import assert_http_bad_request, build_url
from germanium.tools.rest import assert_valid_JSON_response

from .factories import UserFactory, IssueFactory
from .test_case import PystonTestCase


class FilterTestCase(PystonTestCase):

    def test_override_extra_filter_fields(self):
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, filter='created_at__gt="1.1.1980"')))
        assert_valid_JSON_response(
            self.get(build_url(self.USER_API_URL, filter='email contains "test@test.cz"'))
        )

    def test_invalid_filter_format(self):
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, filter='email="test@test.cz" AND')))
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, filter='invalid')))
        assert_http_bad_request(self.get(build_url(self.USER_API_URL,
                                                   filter='email="test@test.cz" AND OR email="test@test.cz"')))

    def test_issue_can_filter_only_with_readable_fields_and_extra_field(self):
        assert_valid_JSON_response(
            self.get(build_url(self.ISSUE_API_URL, filter='solver__created_at="1.1.2017"'))
        )
        assert_valid_JSON_response(self.get(build_url(self.ISSUE_API_URL, filter='created_at>"1.1.2017"')))
        assert_http_bad_request(
            self.get(build_url(self.ISSUE_API_URL, filter='solver__manual_created_date>"1.1.2017"'))
        )

    def test_filter_issue_by_datetime(self):
        now = datetime.now()
        [IssueFactory() for _ in range(5)]

        resp = self.get(build_url(self.ISSUE_API_URL))
        assert_equal(len(self.deserialize(resp)), 5)

        resp = self.get(build_url(self.ISSUE_API_URL, filter='created_at>"{}"'.format(now.isoformat())))
        assert_equal(len(self.deserialize(resp)), 5)

        resp = self.get(build_url(self.ISSUE_API_URL, filter='created_at="{}"'.format(now.isoformat())))
        assert_equal(len(self.deserialize(resp)), 0)

        resp = self.get(build_url(self.ISSUE_API_URL, filter='created_at<"{}"'.format(now.isoformat())))
        assert_equal(len(self.deserialize(resp)), 0)

        resp = self.get(build_url(self.ISSUE_API_URL, filter='created_at contains "{}"'.format(now.date())))
        assert_equal(len(self.deserialize(resp)), 5)

        resp = self.get(build_url(self.ISSUE_API_URL, filter='created_at contains "{}"'.format(now.year)))
        assert_equal(len(self.deserialize(resp)), 5)

        resp = self.get(build_url(self.ISSUE_API_URL,
                                  filter='created_at contains "{}"'.format('{} {}'.format(now.month, now.year))))
        assert_equal(len(self.deserialize(resp)), 5)

        resp = self.get(build_url(self.ISSUE_API_URL,
                                  filter='created_at contains "{}"'.format('{} {}'.format(now.month + 1, now.year))))
        assert_equal(len(self.deserialize(resp)), 0)

        resp = self.get(build_url(self.ISSUE_API_URL, filter='created_at__day = "{}"'.format(now.day)))
        assert_equal(len(self.deserialize(resp)), 5)

        resp = self.get(
            build_url(
                self.ISSUE_API_URL,
                filter='created_at__day = "{}" AND created_at__year = "{}"'.format(now.day, now.year)
            )
        )
        assert_equal(len(self.deserialize(resp)), 5)

        resp = self.get(
            build_url(
                self.ISSUE_API_URL,
                filter='created_at__day = "{}" AND created_at__year = "{}"'.format(now.day + 1, now.year)
            )
        )
        assert_equal(len(self.deserialize(resp)), 0)

        resp = self.get(
            build_url(
                self.ISSUE_API_URL,
                filter='created_at__day = "{}" OR created_at__year = "{}"'.format(now.day + 1, now.year)
            )
        )
        assert_equal(len(self.deserialize(resp)), 5)

        resp = self.get(
            build_url(
                self.ISSUE_API_URL,
                filter='(created_at__day = "{}" AND created_at__year = "{}") OR (created_at > "{}")'.format(
                    now.day + 1, now.year, now.isoformat()
                )
            )
        )
        assert_equal(len(self.deserialize(resp)), 5)

    def test_filter_issue_by_datetime_querystring_filter_parser(self):
        now = datetime.now()
        [IssueFactory() for _ in range(5)]
        resp = self.get(
            build_url(
                self.ISSUE_API_URL, created_at__day=now.day, created_at__year=now.year
            )
        )
        assert_equal(len(self.deserialize(resp)), 5)

        resp = self.get(
            build_url(
                self.ISSUE_API_URL, created_at__day=now.day + 1, created_at__year=now.year
            )
        )
        assert_equal(len(self.deserialize(resp)), 0)

    def test_boolean_filter(self):
        user = UserFactory(is_superuser=False)
        superuser = UserFactory(is_superuser=True)

        data = self.deserialize(self.get(build_url( self.USER_API_URL, is_superuser=0)))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], user.pk)

        data = self.deserialize(self.get(build_url(self.USER_API_URL, is_superuser=1)))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], superuser.pk)

        data = self.deserialize(self.get(build_url( self.USER_API_URL, is_superuser__not=0)))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], superuser.pk)

        data = self.deserialize(self.get(build_url( self.USER_API_URL, is_superuser__gt=0)))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], superuser.pk)

        data = self.deserialize(self.get(build_url( self.USER_API_URL, is_superuser__lt=0)))
        assert_equal(len(data), 0)

        data = self.deserialize(self.get(build_url( self.USER_API_URL, is_superuser__lt=1)))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], user.pk)

        assert_http_bad_request(self.get(build_url(self.USER_API_URL, is_superuser='invalid')))
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, is_superuser=3)))
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, is_superuser__gt=3)))
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, is_superuser__not='invalid')))
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, is_superuser__not='__none__')))

    def test_string_filter(self):
        issue1 = IssueFactory(name='issue with text: protocol')
        issue2 = IssueFactory(name='issue with text: alcohol')

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='name = "issue with text: protocol"')))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='name != "issue with text: protocol"')))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue2.pk)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='name contains "protocol"')))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='name icontains "Protocol"')))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='name startswith "issue"')))
        assert_equal(len(data), 2)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='name iendswith "oL"')))
        assert_equal(len(data), 2)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL, filter='name in ["issue with text: protocol", "issue with text: alcohol"]'
                )
            )
        )
        assert_equal(len(data), 2)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL, filter='name in ["issue with text: protocol", "issue with text"]'
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='name iexact "issue With tExt: prOtocol"')))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

    def test_integer_filter(self):
        issue1 = IssueFactory(logged_minutes=150)
        issue2 = IssueFactory(logged_minutes=31)
        issue3 = IssueFactory(logged_minutes=None)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='logged_minutes = 150')))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='logged_minutes >= 31')))
        assert_equal(len(data), 2)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='logged_minutes <= 150')))
        assert_equal(len(data), 2)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='logged_minutes < 50')))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue2.pk)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='logged_minutes in [null, 150, 31]')))
        assert_equal(len(data), 3)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, filter='logged_minutes = null')))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue3.pk)

    def test_foreign_key_filter(self):
        issue1 = IssueFactory()
        issue2 = IssueFactory(solver=issue1.created_by)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, created_by=issue1.created_by.pk)))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, created_by__not=issue1.created_by.pk)))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue2.pk)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL,
                    created_by__in='[{}, {}]'.format(issue1.created_by.pk, issue2.created_by.pk)
                )
            )
        )
        assert_equal(len(data), 2)

        data = self.deserialize(self.get(build_url(self.ISSUE_API_URL, solver='__none__')))
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

        assert_http_bad_request(self.get(build_url(self.ISSUE_API_URL, solver='invalid')))

    def test_many_to_many_filter(self):
        user1 = UserFactory()
        user2 = UserFactory()

        issue1 = IssueFactory()
        issue2 = IssueFactory()

        issue1.watched_by.add(user1, user2)
        issue2.watched_by.add(user1)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL,
                    watched_by=user2.pk
                )
            )
        )
        assert_equal(len(data), 1)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL,
                    watched_by__in='({},{})'.format(user1.pk, user2.pk)
                )
            )
        )
        assert_equal(len(data), 2)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL,
                    watched_by__in='({})'.format(user1.pk)
                )
            )
        )
        assert_equal(len(data), 2)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL,
                    watched_by__in='({})'.format(user2.pk)
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL,
                    watched_by__all='({},{})'.format(user1.pk, user2.pk)
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL,
                    watched_by__all='({})'.format(user1.pk)
                )
            )
        )
        assert_equal(len(data), 2)

    def test_many_to_one_filter(self):
        issue1 = IssueFactory()
        issue2 = IssueFactory()
        issue3 = IssueFactory(created_by=issue1.created_by)

        user1 = issue1.created_by

        assert_http_bad_request(self.get(build_url(self.USER_API_URL, created_issues=user1)))

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    created_issues__in='({},{})'.format(issue1.pk, issue3.pk)
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], user1.pk)

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    created_issues__in='({})'.format(issue1.pk)
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], user1.pk)

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    created_issues__in='({},{},{})'.format(issue1.pk, issue2.pk, issue3.pk)
                )
            )
        )
        assert_equal(len(data), 2)

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    created_issues__all='({},{},{})'.format(issue1.pk, issue2.pk, issue3.pk)
                )
            )
        )
        assert_equal(len(data), 0)

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    created_issues__all='({},{})'.format(issue1.pk, issue3.pk)
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], user1.pk)

    def test_custom_field_filter(self):
        user = UserFactory(email='test1@email.com')

        assert_http_bad_request(self.get(build_url(self.USER_API_URL, email='test1@email.com')))
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, email__icontains='test1')))
        assert_http_bad_request(self.get(build_url(self.USER_API_URL, email__not='test1')))

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    email__contains='test'
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], user.pk)

    def test_custom_method_filter(self):
        user1 = UserFactory()
        user2 = UserFactory()

        issue1 = IssueFactory()
        issue2 = IssueFactory()

        issue1.watched_by.add(user1, user2)
        issue2.watched_by.add(user1)

        assert_http_bad_request(self.get(build_url(self.USER_API_URL, watched_issues_count='invalid')))

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    watched_issues_count=2
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], user1.pk)

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    watched_issues_count=1
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], user2.pk)

    def test_filter_by_decorator(self):
        issue1 = IssueFactory(description='test1')
        issue2 = IssueFactory(description='test2')

        assert_http_bad_request(self.get(build_url(self.ISSUE_API_URL, description='test1')))

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL,
                    short_description__contains='test'
                )
            )
        )
        assert_equal(len(data), 2)

        data = self.deserialize(
            self.get(
                build_url(
                    self.ISSUE_API_URL,
                    short_description='test1'
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], issue1.pk)

    def test_resource_filter(self):
        user1 = UserFactory()
        user2 = UserFactory()

        IssueFactory(solver=user1, logged_minutes=120, estimate_minutes=60)
        IssueFactory(solver=user2, logged_minutes=59, estimate_minutes=60)

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    issues__overtime=1
                )
            )
        )
        assert_equal(len(data), 1)
        assert_equal(data[0]['id'], user1.pk)

        data = self.deserialize(
            self.get(
                build_url(
                    self.USER_API_URL,
                    issues__overtime=0,
                )
            )
        )
        assert_equal(len(data), 5)
