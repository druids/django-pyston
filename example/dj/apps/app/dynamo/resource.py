from pyston.filters.utils import OperatorSlug
from pyston.contrib.dynamo.resource import BaseDynamoResource
from pyston.contrib.dynamo.filter import BaseDynamoFilter

from .models import Comment


class UserIDFilter(BaseDynamoFilter):

    allowed_operators = (OperatorSlug.EQ,)

    def get_filter_term(self, value, operator_slug, request):
        return {'user_id__startswith': value}


class CommentDynamoResource(BaseDynamoResource):

    model = Comment
    fields = (
        'issue_id', 'user_id', 'content', 'is_public', 'priority'
    )
    filters = {
        'user_id': UserIDFilter,
    }

    can_read_obj = True
    range_key = 'user_id'

    def _get_hash_key(self):
        return self.kwargs.get('issue_pk')
