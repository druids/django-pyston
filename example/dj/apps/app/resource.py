from __future__ import unicode_literals

from pyston.resource import BaseModelResource, BaseResource, BaseObjectResource
from pyston.response import RESTCreatedResponse, RESTOkResponse
from pyston.serializer import SerializableObj

from .models import Issue, User
from .serializable import CountIssuesPerUserTable, CountWatchersPerIssue


class IssueResource(BaseModelResource):

    model = Issue
    fields = ('id', 'created_at', '_obj_name', 'name', ('created_by', ('id', 'contract',)), 'solver',
              'leader', 'watched_by')
    detailed_fields = ('id', 'created_at', '_obj_name', 'name', ('created_by', ('id', 'contract',)), 'solver',
                       'leader', 'watched_by')
    general_fields = ('id', '_obj_name', 'name', 'created_by', 'watched_by')


class UserResource(BaseModelResource):

    model = User


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
        return RESTOkResponse({
            'foo_bar': 'foo bar',
            'connected': connected,
        })

    def post(self):
        data = self.get_dict_data()
        return RESTCreatedResponse({'bar_baz': data.get('bar_baz')})
