.. _dynamodb:

DynamoDB
========

Library has support for DynamoDB database. For this purpose you must have installed ``pydjamodb`` library. Next you can use special resource base class to implement DynamoDB REST endpoint::

    from pydjamodb.models import Dynamo
    from pynamodb.attributes import (
        MapAttribute, NumberAttribute, UnicodeAttribute, UTCDateTimeAttribute, BooleanAttribute, NumberAttribute
    )

    class Comment(Dynamo):

        issue_id = UnicodeAttribute(hash_key=True)
        user_id = UnicodeAttribute(range_key=True)
        content = UnicodeAttribute()
        is_public = BooleanAttribute()
        priority = NumberAttribute()

        def __str__(self):
            return self.id

        class Meta:
            table_name = 'comment'


    from pyston.filters.filters import OPERATORS
    from pyston.contrib.dynamo.resource import BaseDynamoResource
    from pyston.contrib.dynamo.filter import BaseDynamoFilter

    class UserIdFilter(BaseDynamoFilter):

        allowed_operators = (OPERATORS.EQ,)

        def get_filter_term(self, value, operator_slug, request):
            return {f'user_id__startswith': value}


    class CommentDynamoResource(BaseDynamoResource):

        model = Comment
        fields = (
            'issue_id', 'user_id', 'content', 'is_public', 'priority'
        )
        filters = {
            'user_id': UserIdFilter,
        }

        can_read_obj = True
        range_key = 'user_id'

        def _get_hash_key(self):
            return self.kwargs.get('issue_pk')


Due database restrictions resource ordering can be performed only via range key. Filters must be added by hand like in the example. Pagination is performed via cursor based paginator.

Right now ``BaseDynamoResource`` support only reading from the database.
