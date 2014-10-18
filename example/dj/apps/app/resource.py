from piston.resource import BaseModelResource, BaseResource

from .models import Issue, User


class IssueResource(BaseModelResource):
    model = Issue
    default_detailed_fields = ('id', '_obj_name', 'name', 'created_by', 'watched_by', 'solver', 'leader')
    fields = ('id', '_obj_name', 'name')


class UserResource(BaseModelResource):
    model = User
    default_detailed_fields = ('id', '_obj_name', 'email', 'contract')
    fields = ('id', '_obj_name', 'email')


class ExtraResource(BaseResource):

    def get(self):
        return {'extra': 1}
