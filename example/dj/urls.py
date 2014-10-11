from django.conf.urls import patterns, url

from app.resource import IssueResource, UserResource


urlpatterns = patterns('',
    url(r'^api/user/$', UserResource.as_view(allowed_methods=('GET', 'POST', 'HEAD', 'OPTIONS'))),
    url(r'^api/user/(?P<pk>\d+)/$', UserResource.as_view(allowed_methods=('GET', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))),
    url(r'^api/issue/$', IssueResource.as_view(allowed_methods=('GET', 'POST', 'HEAD', 'OPTIONS'))),
    url(r'^api/issue/(?P<pk>\d+)/$', IssueResource.as_view(allowed_methods=('GET', 'PUT', 'DELETE', 'HEAD', 'OPTIONS')))
)
