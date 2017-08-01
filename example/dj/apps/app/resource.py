from __future__ import unicode_literals

from django.db.models import F, Q

from pyston.resource import BaseModelResource, BaseResource, BaseObjectResource
from pyston.response import RESTCreatedResponse, RESTOkResponse
from pyston.serializer import SerializableObj
from pyston.forms import RESTModelForm, ReverseOneToOneField, ReverseManyField
from pyston.filters.default_filters import SimpleEqualFilter, BooleanFilterMixin

from .models import Issue, User
from .serializable import CountIssuesPerUserTable, CountWatchersPerIssue


class OvertimeIssuesFilter(BooleanFilterMixin, SimpleEqualFilter):

    def get_filter_term(self, value, operator, request):
        filter_term = Q(**{
            'solving_issue__in': Issue.objects.filter(logged_minutes__gt=F('estimate_minutes')).values('pk')
        })
        return filter_term if value else ~filter_term


class IssueResource(BaseModelResource):

    model = Issue
    fields = ('id', 'created_at', '_obj_name', 'name', ('created_by', ('id', 'contract', 'created_at')), 'solver',
              'leader', 'watched_by', 'logged_minutes')
    detailed_fields = ('id', 'created_at', '_obj_name', 'name', ('created_by', ('id', 'contract',)), 'solver',
                       'leader', 'watched_by')
    general_fields = ('id', '_obj_name', 'name', ('created_by', ('id', 'contract', 'created_at')), 'watched_by',
                      'short_description')

    create_obj_permission = True
    read_obj_permission = True
    update_obj_permission = True
    delete_obj_permission = True


class UserResource(BaseModelResource):

    model = User
    DATA_KEY_MAPPING = {
        'created_at': 'createdAt',
        'solving_issue': 'solvingIssue',
        'first_name': 'firstName',
        'last_name': 'lastName',
        'is_superuser': 'isSuperuser',
        'watched_issues': 'watchedIssues',
        'created_issues': 'createdIssues',
        'manual_created_date': 'manualCreatedDate',
        'watched_issues_count': 'watchedIssuesCount',
    }
    create_obj_permission = True
    read_obj_permission = True
    update_obj_permission = True
    delete_obj_permission = True
    extra_order_fields = ()
    extra_filter_fields = ()
    filters = {
        'issues__overtime': OvertimeIssuesFilter
    }


class ExtraResource(BaseResource):

    def get(self):
        return {'extra': 1}


class CountIssuesPerUserResource(BaseResource):

    def get(self):
        return CountIssuesPerUserTable()


class CountWatchersPerIssueResource(BaseResource):

    def get(self):
        return [CountWatchersPerIssue(issue) for issue in Issue.objects.all()]


class TestTextObject(SerializableObj):

    def __init__(self, fiz_baz):
        self.fiz_baz = fiz_baz

    class RESTMeta:
        fields = ('fiz_baz',)


class TestTextObjectCamelCaseResource(BaseObjectResource):

    model = TestTextObject
    register = True

    read_obj_permission = True

    DATA_KEY_MAPPING = {
        'fiz_baz': 'fizBaz',
    }


class TestCamelCaseResource(BaseResource):

    DATA_KEY_MAPPING = {
        'bar_baz': 'barBaz',
        'foo_bar': 'fooBar',
    }

    def get(self):
        connected = TestTextObject('test object property content')
        return {
            'foo_bar': 'foo bar',
            'connected': connected,
        }

    def post(self):
        data = self.get_dict_data()
        return RESTCreatedResponse({'bar_baz': data.get('bar_baz')})


class UserForm(RESTModelForm):

    watched_issues = ReverseManyField('watched_issues')
    created_issues_renamed = ReverseManyField('created_issues')
    solving_issue_renamed = ReverseOneToOneField('solving_issue')
    leading_issue_renamed = ReverseOneToOneField('leading_issue')


class UserWithFormResource(BaseModelResource):

    register = False
    model = User
    form_class = UserForm
    create_obj_permission = True
    read_obj_permission = True
    update_obj_permission = True
    delete_obj_permission = True
