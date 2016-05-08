import django
from django.conf.urls import patterns, url

from app.resource import IssueResource, UserResource, ExtraResource

urlpatterns = [
    url(r'^api/user/$', UserResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/user/(?P<pk>\d+)/$', UserResource.as_view(allowed_methods=('get', 'put', 'delete', 'head', 'options'))),
    url(r'^api/issue/$', IssueResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/issue/(?P<pk>\d+)/$', IssueResource.as_view(allowed_methods=('get', 'put', 'delete', 'head', 'options'))),
    url(r'^api/extra/$', ExtraResource.as_view())
]

if django.get_version() < '1.9':
    urlpatterns = patterns('', *urlpatterns)
