from __future__ import unicode_literals

from pyston.resource import BaseModelResource, BaseResource

from .models import Issue, User
from .serializable import CountIssuesPerUserTable, CountWatchersPerIssue


class IssueResource(BaseModelResource):

    model = Issue
    fields = ('id', 'created_at', '_obj_name', 'name', ('created_by', ('id', 'contract',)), 'solver',
              'leader', 'watched_by')
    default_detailed_fields = ('id', 'created_at', '_obj_name', 'name', ('created_by', ('id', 'contract',)), 'solver',
                               'leader', 'watched_by')
    default_general_fields = ('id', '_obj_name', 'name', 'created_by', 'watched_by')


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
