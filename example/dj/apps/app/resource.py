from piston.resource import BaseModelResource

from .models import Issue, User


class IssueResource(BaseModelResource):
    model = Issue


class UserResource(BaseModelResource):
    model = User
    default_detailed_fields = ('id', '_obj_name', 'email')
    fields = ('id', '_obj_name', 'email')
