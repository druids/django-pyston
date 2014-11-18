from piston.resource import BaseModelResource, BaseResource
from piston.utils import RFS

from .models import Issue, User


class IssueResource(BaseModelResource):
    model = Issue
    default_detailed_fields = ('id', '_obj_name', 'name', ('created_by', ('contract',)), 'solver', 'leader')
    default_general_fields = ('id', '_obj_name', 'name', 'created_by', 'watched_by')


class UserResource(BaseModelResource):
    model = User
    default_detailed_fields = ('id', '_obj_name', 'email', 'contract')
    default_general_fields = RFS('id', '_obj_name', 'email')


class ExtraResource(BaseResource):

    def get(self):
        return {'extra': 1}
