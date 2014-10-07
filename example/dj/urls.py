from django.conf.urls import patterns, url

from app.resource import IssueResource, UserResource


urlpatterns = patterns('',
    url(r'^api/user/$', UserResource.as_view(allowed_methods=('GET', 'POST'))),
    url(r'^api/user/(?P<pk>\d+)/$', UserResource.as_view(allowed_methods=('GET', 'PUT', 'DELETE'))),
    url(r'^api/issue/$', UserResource.as_view(allowed_methods=('GET', 'POST'))),
    url(r'^api/issue/(?P<pk>\d+)/$', UserResource.as_view(allowed_methods=('GET', 'PUT', 'DELETE')))
)
