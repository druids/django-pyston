from pyston.contrib.elasticsearch.resource import BaseElasticsearchResource

from .models import Comment


class CommentElasticsearchResource(BaseElasticsearchResource):

    model = Comment
    fields = (
        'id', 'user_id', 'content', 'is_public', 'priority'
    )

    can_read_obj = True
