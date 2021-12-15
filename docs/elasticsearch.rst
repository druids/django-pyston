.. _elasticsearch:

Elasticsearch
=============

Library has support for elasticsearch database. For this purpose you must have installed ``elasticsearch`` and ``elasticsearch-dsl`` libraries. Next you can use special resource base class to implement elasticsearch REST endpoint::

    from elasticsearch_dsl import Document, Date, Integer, Keyword, Text, Boolean

    class Comment(Document):
        user_id = Keyword()
        content = Text()
        is_public = Boolean()
        priority = Integer()

        @property
        def id(self):
            return self.meta.id

        def __str__(self):
            return self.id

        class Index:
            name = 'comment'


    from pyston.contrib.elasticsearch.resource import BaseElasticsearchResource

    class CommentElasticsearchResource(BaseElasticsearchResource):

        model = Comment
        fields = (
            'id', 'user_id', 'content', 'is_public', 'priority'
        )

        can_read_obj = True


Filtering, ordering and pagination is automatically added to the resource with the same was as ``BaseDjangoResource``.

Right now ``BaseElasticsearchResource`` support only reading from the database.
