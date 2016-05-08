from unittest.case import TestCase

from django.core.exceptions import FieldError

from germanium.tools import assert_true, assert_false, assert_raises, assert_equal, assert_is_none

from pyston.utils.compatibility import (
    is_relation, is_one_to_one, is_many_to_many, is_many_to_one, is_reverse_many_to_many, is_reverse_many_to_one,
    is_reverse_one_to_one, get_model_from_relation, get_model_from_relation_or_none, get_reverse_field_name
)

from app.models import Issue, User


class CompatibilityTestCase(TestCase):

    def test_is_relation(self):
        assert_true(is_relation(Issue, 'watched_by'))
        assert_true(is_relation(Issue, 'created_by'))
        assert_true(is_relation(Issue, 'solver'))
        assert_true(is_relation(Issue, 'leader'))
        assert_false(is_relation(Issue, 'name'))
        assert_false(is_relation(Issue, 'created_at'))
        assert_false(is_relation(Issue, 'invalid'))

        assert_true(is_relation(User, 'watched_issues'))
        assert_true(is_relation(User, 'created_issues'))
        assert_true(is_relation(User, 'solving_issue'))
        assert_true(is_relation(User, 'leading_issue'))

    def test_is_one_to_one(self):
        assert_false(is_one_to_one(Issue, 'watched_by'))
        assert_false(is_one_to_one(Issue, 'created_by'))
        assert_true(is_one_to_one(Issue, 'solver'))
        assert_true(is_one_to_one(Issue, 'leader'))
        assert_false(is_one_to_one(Issue, 'name'))
        assert_false(is_one_to_one(Issue, 'created_at'))
        assert_false(is_one_to_one(Issue, 'invalid'))

        assert_false(is_one_to_one(User, 'watched_issues'))
        assert_false(is_one_to_one(User, 'created_issues'))
        assert_false(is_one_to_one(User, 'solving_issue'))
        assert_false(is_one_to_one(User, 'leading_issue'))

    def test_is_many_to_one(self):
        assert_false(is_many_to_one(Issue, 'watched_by'))
        assert_true(is_many_to_one(Issue, 'created_by'))
        assert_false(is_many_to_one(Issue, 'solver'))
        assert_false(is_many_to_one(Issue, 'leader'))
        assert_false(is_many_to_one(Issue, 'name'))
        assert_false(is_many_to_one(Issue, 'created_at'))
        assert_false(is_many_to_one(Issue, 'invalid'))

        assert_false(is_many_to_one(User, 'watched_issues'))
        assert_false(is_many_to_one(User, 'created_issues'))
        assert_false(is_many_to_one(User, 'solving_issue'))
        assert_false(is_many_to_one(User, 'leading_issue'))

    def test_is_many_to_many(self):
        assert_true(is_many_to_many(Issue, 'watched_by'))
        assert_false(is_many_to_many(Issue, 'created_by'))
        assert_false(is_many_to_many(Issue, 'solver'))
        assert_false(is_many_to_many(Issue, 'leader'))
        assert_false(is_many_to_many(Issue, 'name'))
        assert_false(is_many_to_many(Issue, 'created_at'))
        assert_false(is_many_to_many(Issue, 'invalid'))

        assert_false(is_many_to_many(User, 'watched_issues'))
        assert_false(is_many_to_many(User, 'created_issues'))
        assert_false(is_many_to_many(User, 'solving_issue'))
        assert_false(is_many_to_many(User, 'leading_issue'))

    def test_is_reverse_one_to_one(self):
        assert_false(is_reverse_one_to_one(Issue, 'watched_by'))
        assert_false(is_reverse_one_to_one(Issue, 'created_by'))
        assert_false(is_reverse_one_to_one(Issue, 'solver'))
        assert_false(is_reverse_one_to_one(Issue, 'leader'))
        assert_false(is_reverse_one_to_one(Issue, 'name'))
        assert_false(is_reverse_one_to_one(Issue, 'created_at'))
        assert_false(is_reverse_one_to_one(Issue, 'invalid'))

        assert_false(is_reverse_one_to_one(User, 'watched_issues'))
        assert_false(is_reverse_one_to_one(User, 'created_issues'))
        assert_true(is_reverse_one_to_one(User, 'solving_issue'))
        assert_true(is_reverse_one_to_one(User, 'leading_issue'))

    def test_is_reverse_many_to_one(self):
        assert_false(is_reverse_many_to_one(Issue, 'watched_by'))
        assert_false(is_reverse_many_to_one(Issue, 'created_by'))
        assert_false(is_reverse_many_to_one(Issue, 'solver'))
        assert_false(is_reverse_many_to_one(Issue, 'leader'))
        assert_false(is_reverse_many_to_one(Issue, 'name'))
        assert_false(is_reverse_many_to_one(Issue, 'created_at'))
        assert_false(is_reverse_many_to_one(Issue, 'invalid'))

        assert_false(is_reverse_many_to_one(User, 'watched_issues'))
        assert_true(is_reverse_many_to_one(User, 'created_issues'))
        assert_false(is_reverse_many_to_one(User, 'solving_issue'))
        assert_false(is_reverse_many_to_one(User, 'leading_issue'))

    def test_is_reverse_many_to_many(self):
        assert_false(is_reverse_many_to_many(Issue, 'watched_by'))
        assert_false(is_reverse_many_to_many(Issue, 'created_by'))
        assert_false(is_reverse_many_to_many(Issue, 'solver'))
        assert_false(is_reverse_many_to_many(Issue, 'leader'))
        assert_false(is_reverse_many_to_many(Issue, 'name'))
        assert_false(is_reverse_many_to_many(Issue, 'created_at'))
        assert_false(is_reverse_many_to_many(Issue, 'invalid'))

        assert_true(is_reverse_many_to_many(User, 'watched_issues'))
        assert_false(is_reverse_many_to_many(User, 'created_issues'))
        assert_false(is_reverse_many_to_many(User, 'solving_issue'))
        assert_false(is_reverse_many_to_many(User, 'leading_issue'))

    def test_get_model_from_relation(self):
        assert_equal(get_model_from_relation(Issue, 'watched_by'), User)
        assert_equal(get_model_from_relation(Issue, 'created_by'), User)
        assert_equal(get_model_from_relation(Issue, 'solver'), User)
        assert_equal(get_model_from_relation(Issue, 'leader'), User)
        assert_raises(FieldError, get_model_from_relation, Issue, 'name')
        assert_raises(FieldError, get_model_from_relation, Issue, 'created_at')
        assert_raises(FieldError, get_model_from_relation, Issue, 'invalid')

        assert_equal(get_model_from_relation(User, 'watched_issues'), Issue)
        assert_equal(get_model_from_relation(User, 'created_issues'), Issue)
        assert_equal(get_model_from_relation(User, 'solving_issue'), Issue)
        assert_equal(get_model_from_relation(User, 'leading_issue'), Issue)

    def test_get_model_from_relation_or_none(self):
        assert_equal(get_model_from_relation_or_none(Issue, 'watched_by'), User)
        assert_equal(get_model_from_relation_or_none(Issue, 'created_by'), User)
        assert_equal(get_model_from_relation_or_none(Issue, 'solver'), User)
        assert_equal(get_model_from_relation_or_none(Issue, 'leader'), User)
        assert_is_none(get_model_from_relation_or_none(Issue, 'name'))
        assert_is_none(get_model_from_relation_or_none(Issue, 'created_at'))
        assert_is_none(get_model_from_relation_or_none(Issue, 'invalid'))

        assert_equal(get_model_from_relation_or_none(User, 'watched_issues'), Issue)
        assert_equal(get_model_from_relation_or_none(User, 'created_issues'), Issue)
        assert_equal(get_model_from_relation_or_none(User, 'solving_issue'), Issue)
        assert_equal(get_model_from_relation_or_none(User, 'leading_issue'), Issue)

    def test_get_reverse_field_name(self):
        assert_equal(get_reverse_field_name(Issue, 'watched_by'), 'watched_issues')
        assert_equal(get_reverse_field_name(Issue, 'created_by'), 'created_issues')
        assert_equal(get_reverse_field_name(Issue, 'solver'), 'solving_issue')
        assert_equal(get_reverse_field_name(Issue, 'leader'), 'leading_issue')
        assert_raises(FieldError, get_reverse_field_name, Issue, 'name')
        assert_raises(FieldError, get_reverse_field_name, Issue, 'created_at')
        assert_raises(FieldError, get_reverse_field_name, Issue, 'invalid')

        assert_equal(get_reverse_field_name(User, 'watched_issues'), 'watched_by')
        assert_equal(get_reverse_field_name(User, 'created_issues'), 'created_by')
        assert_equal(get_reverse_field_name(User, 'solving_issue'), 'solver')
        assert_equal(get_reverse_field_name(User, 'leading_issue'), 'leader')
