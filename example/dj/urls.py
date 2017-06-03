from distutils.version import StrictVersion

import django
from django.conf.urls import url

from app.resource import (IssueResource, UserResource, ExtraResource, CountIssuesPerUserResource,
                          CountWatchersPerIssueResource, TestCamelCaseResource,
                          CountWatchersPerIssueResource, UserResource, UserWithFormResource)

urlpatterns = [
    url(r'^api/user/$', UserResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/user-form/$', UserWithFormResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/user/(?P<pk>\d+)/$', UserResource.as_view(
        allowed_methods=('get', 'put', 'patch', 'delete', 'head', 'options')
    )),
    url(r'^api/test-cc/$', TestCamelCaseResource.as_view(allowed_methods=('get', 'post',))),
    url(r'^api/issue/$', IssueResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/issue/(?P<pk>\d+)/$',
        IssueResource.as_view(allowed_methods=('get', 'put', 'patch', 'delete', 'head', 'options'))),
    url(r'^api/extra/$', ExtraResource.as_view()),
    url(r'^api/count-issues-per-user/$', CountIssuesPerUserResource.as_view()),
    url(r'^api/count-watchers-per-issue/$', CountWatchersPerIssueResource.as_view()),
]

if StrictVersion(django.get_version()) < StrictVersion('1.9'):
    from django.conf.urls import patterns

    urlpatterns = patterns('', *urlpatterns)
