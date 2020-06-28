from django import forms
from django.db.models import F, Q
from pyston.converters import XMLConverter
from pyston.filters.default_filters import BooleanFilterMixin, SimpleEqualFilter
from pyston.forms import (
    ISODateTimeField, MultipleRelatedField, RESTModelForm, RESTValidationError, ReverseManyField, ReverseOneToOneField,
    SingleRelatedField
)
from pyston.forms.postgres import RESTSimpleArrayField
from pyston.resource import BaseModelResource, BaseObjectResource, BaseResource
from pyston.response import RESTCreatedResponse
from pyston.serializer import SerializableObj

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

    converter_classes = (
        'pyston.converters.JSONConverter',
        XMLConverter,
    )
    can_create_obj = True
    can_read_obj = True
    can_update_obj = True
    can_delete_obj = True

    def _obj_name(self, obj):
        return str(obj)


class UserResource(BaseModelResource):

    model = User
    renamed_fields = {
        'createdAt': 'created_at',
        'solvingIssue': 'solving_issue',
        'firstName': 'first_name',
        'lastName': 'last_name',
        'isSuperuser': 'is_superuser',
        'watchedIssues': 'watched_issues',
        'createdIssues': 'created_issues',
        'manualCreatedDate': 'manual_created_date',
        'watchedIssuesCount': 'watched_issues_count',
    }
    fields = (
        'createdAt', 'email', 'contract', 'solvingIssue', 'firstName', 'lastName', 'isSuperuser', 'manualCreatedDate',
        'watchedIssuesCount'
    )
    detailed_fields = (
        'createdAt', 'email', 'contract', 'solvingIssue', 'firstName', 'lastName', 'watchedIssues',
        'createdIssues__id', 'manualCreatedDate'
    )
    general_fields = (
        'email', 'firstName', 'lastName', 'watchedIssues__name', 'watchedIssues__id', 'manualCreatedDate',
        'watchedIssuesCount'
    )
    extra_fields = ()
    can_create_obj = True
    can_read_obj = True
    can_update_obj = True
    can_delete_obj = True
    extra_order_fields = ()
    extra_filter_fields = ()
    filters = {
        'issues__overtime': OvertimeIssuesFilter
    }
    field_labels = {
        'email': 'E-mail address',
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

    class Meta:
        fields = ('fiz_baz',)


class TestTextObjectCamelCaseResource(BaseObjectResource):

    model = TestTextObject
    register = True

    can_read_obj = True

    renamed_fields = {
        'fizBaz': 'fiz_baz',
    }
    fields = ('fizBaz',)


class TestCamelCaseResource(BaseResource):

    def get(self):
        connected = TestTextObject('test object property content')
        return {
            'fooBar': 'foo bar',
            'connected': connected,
        }


class UserForm(RESTModelForm):

    watched_issues = ReverseManyField('watched_issues')
    created_issues_renamed = ReverseManyField('created_issues')
    solving_issue_renamed = ReverseOneToOneField('solving_issue')
    leading_issue_renamed = ReverseOneToOneField('leading_issue')

    def clean_created_issues_renamed(self):
        created_issues = self.cleaned_data.get('created_issues_renamed')
        if created_issues and any(issue.name == 'invalid' for issue in created_issues):
            raise RESTValidationError('Invalid issue name')


class UserWithFormResource(BaseModelResource):

    register = False
    model = User
    form_class = UserForm
    can_create_obj = True
    can_read_obj = True
    can_update_obj = True
    can_delete_obj = True

    fields = ('user_email',)

    def user_email(self, obj):
        return obj.email


class IssueForm(RESTModelForm):

    created_by = SingleRelatedField('created_by')
    leader = SingleRelatedField('leader', is_allowed_foreign_key=False)
    another_users = MultipleRelatedField('watched_by', form_field=forms.ModelMultipleChoiceField(
        queryset=User.objects.all(), required=False
    ), is_allowed_foreign_key=False)
    tags_list = RESTSimpleArrayField(label='tags', base_field=forms.CharField(max_length=5), required=False)
    iso_date = ISODateTimeField(required=False)

    def save(self, commit=True):
        instance = super().save(commit=False)
        tags_list = self.cleaned_data.get('tags_list')
        if tags_list:
            instance.tags = '|'.join(tags_list)
        if commit:
            instance.save()
        return instance

    class Meta:
        exclude = ('tags',)


class IssueWithFormResource(BaseModelResource):

    register = False
    model = Issue
    form_class = IssueForm
    can_create_obj = True
    can_read_obj = True
    can_update_obj = True
    can_delete_obj = True

    fields = ('id', 'creator')
    resource_typemapper = {
        User: UserWithFormResource,
    }

    def creator(self, obj):
        return obj.created_by
