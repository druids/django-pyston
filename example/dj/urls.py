from django.conf import settings
from django.conf.urls import url

from app.dynamo.resource import CommentDynamoResource
from app.elasticsearch.resource import CommentElasticsearchResource
from app.resource import (
    IssueResource, UserResource, ExtraResource, CountIssuesPerUserResource, CountWatchersPerIssueResource,
    TestCamelCaseResource, CountWatchersPerIssueResource, UserResource, UserWithFormResource, IssueWithFormResource
)


urlpatterns = [
    url(r'^api/user/$', UserResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/user-form/$', UserWithFormResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/user/(?P<pk>\d+)/$', UserResource.as_view(
        allowed_methods=('get', 'put', 'patch', 'delete', 'head', 'options')
    )),
    url(r'^api/test-cc/$', TestCamelCaseResource.as_view(allowed_methods=('get', 'post',))),
    url(r'^api/issue/$', IssueResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/issue-form/$', IssueWithFormResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/issue/(?P<pk>\d+)/$',
        IssueResource.as_view(allowed_methods=('get', 'put', 'patch', 'delete', 'head', 'options'))),
    url(r'^api/extra/$', ExtraResource.as_view()),
    url(r'^api/count-issues-per-user/$', CountIssuesPerUserResource.as_view()),
    url(r'^api/count-watchers-per-issue/$', CountWatchersPerIssueResource.as_view()),
    url(r'^api/elasticsearch-comment/$', CommentElasticsearchResource.as_view()),
    url(r'^api/elasticsearch-comment/(?P<pk>\d+)/$', CommentElasticsearchResource.as_view()),
    url(r'^api/issue/(?P<issue_pk>\d+)/Dynamo-comment/$', CommentDynamoResource.as_view()),
    url(r'^api/issue/(?P<issue_pk>\d+)/Dynamo-comment/(?P<pk>\d+)/$', CommentDynamoResource.as_view()),
]
