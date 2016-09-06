from distutils.version import StrictVersion

import django
from django.conf.urls import url

from app.resource import IssueResource, UserResource, ExtraResource

urlpatterns = [
    url(r'^api/user/$', UserResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/user/(?P<pk>\d+)/$', UserResource.as_view(allowed_methods=('get', 'put', 'delete', 'head', 'options'))),
    url(r'^api/issue/$', IssueResource.as_view(allowed_methods=('get', 'post', 'head', 'options'))),
    url(r'^api/issue/(?P<pk>\d+)/$', IssueResource.as_view(allowed_methods=('get', 'put', 'delete', 'head', 'options'))),
    url(r'^api/extra/$', ExtraResource.as_view())
]

if StrictVersion(django.get_version()) < StrictVersion('1.9'):
    from django.conf.urls import patterns

    urlpatterns = patterns('', *urlpatterns)
