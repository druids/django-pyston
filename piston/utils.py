from __future__ import unicode_literals

from django.http import HttpResponse
from django.utils.translation import ugettext as _
from django.db.models.fields.related import RelatedField
from django.shortcuts import _get_queryset
from django.http.response import Http404
from django.template.defaultfilters import lower
from django.db import models


class rc_factory(object):
    """
    Status codes.
    """
    CODES = dict(
        ALL_OK=({'success': _('OK')}, 200),
        CREATED=({'success': _('The record was created')}, 201),
        DELETED=('', 204),  # 204 says "Don't send a body!"
        BAD_REQUEST=({'error': _('Bad Request')}, 400),
        FORBIDDEN=({'error':_('Forbidden')}, 403),
        NOT_FOUND=({'error':_('Not Found')}, 404),
        METHOD_NOT_ALLOWED=({'error': _('Method Not Allowed')}, 405),
        DUPLICATE_ENTRY=({'error': _('Conflict/Duplicate')}, 409),
        NOT_HERE=({'error': _('Gone')}, 410),
        UNSUPPORTED_MEDIA_TYPE=({'error': _('Unsupported Media Type')}, 415),
        INTERNAL_ERROR=({'error': _('Internal server error')}, 500),
        NOT_IMPLEMENTED=({'error': _('Not implemented')}, 501),
        THROTTLED=({'error': _('The resource was throttled')}, 503)
    )

    def __getattr__(self, attr):
        """
        Returns a fresh `HttpResponse` when getting
        an "attribute". This is backwards compatible
        with 0.2, which is important.
        """
        try:
            (r, c) = self.CODES.get(attr)
        except TypeError:
            raise AttributeError(attr)

        class HttpResponseWrapper(HttpResponse):
            """
            Wrap HttpResponse and make sure that the internal_base_content_is_iter 
            flag is updated when the _set_content method (via the content
            property) is called
            """
            def _set_content(self, content):
                """
                type of the value parameter. This logic is in the construtor
                for HttpResponse, but doesn't get repeated when setting
                HttpResponse.content although this bug report (feature request)
                suggests that it should: http://code.djangoproject.com/ticket/9403
                """
                if not isinstance(content, basestring) and hasattr(content, '__iter__'):
                    self._container = {'messages': content}
                    self._base_content_is_iter = True
                else:
                    self._container = [content]
                    self._base_content_is_iter = False

            content = property(HttpResponse.content.getter, _set_content)

        return HttpResponseWrapper(r, content_type='text/plain', status=c)

rc = rc_factory()


def coerce_put_post(request):
    """
    Django doesn't particularly understand REST.
    In case we send data over PUT, Django won't
    actually look at the data and load it. We need
    to twist its arm here.
    
    The try/except abominiation here is due to a bug
    in mod_python. This should fix it.
    """
    if request.method == "PUT":
        # Bug fix: if _load_post_and_files has already been called, for
        # example by middleware accessing request.POST, the below code to
        # pretend the request is a POST instead of a PUT will be too late
        # to make a difference. Also calling _load_post_and_files will result
        # in the following exception:
        #   AttributeError: You cannot set the upload handlers after the upload has been processed.
        # The fix is to check for the presence of the _post field which is set
        # the first time _load_post_and_files is called (both by wsgi.py and
        # modpython.py). If it's set, the request has to be 'reset' to redo
        # the query value parsing in POST mode.
        if hasattr(request, '_post'):
            del request._post
            del request._files

        try:
            request.method = "POST"
            request._load_post_and_files()
            request.method = "PUT"
        except AttributeError:
            request.META['REQUEST_METHOD'] = 'POST'
            request._load_post_and_files()
            request.META['REQUEST_METHOD'] = 'PUT'

        request.PUT = request.POST


def model_default_rest_fields(model):
    rest_fields = []
    for field in model._meta.fields:
        if isinstance(field, RelatedField):
            rest_fields.append((field.name, ('id', '_obj_name', '_rest_links')))
        else:
            rest_fields.append(field.name)
    return rest_fields


def list_to_dict(list_obj):
    dict_obj = {}
    for val in list_obj:
        if isinstance(val, (list, tuple)):
            dict_obj[val[0]] = list_to_dict(val[1])
        else:
            dict_obj[val] = {}
    return dict_obj


def dict_to_list(dict_obj):
    list_obj = []
    for key, val in dict_obj.items():
        if val:
            list_obj.append((key, dict_to_list(val)))
        else:
            list_obj.append(key)
    return tuple(list_obj)


def join_dicts(dict_obj1, dict_obj2):
    joined_dict = dict_obj1.copy()

    for key2, val2 in dict_obj2.items():
        val1 = joined_dict.get(key2)
        if not val1:
            joined_dict[key2] = val2
        elif not val2:
            continue
        else:
            joined_dict[key2] = join_dicts(val1, val2)
    return joined_dict


def flat_list(list_obj):
    flat_list_obj = []
    for val in list_obj:
        if isinstance(val, (list, tuple)):
            flat_list_obj.append(val[0])
        else:
            flat_list_obj.append(val)
    return flat_list_obj


class JsonObj(dict):

    def __setattr__(self, name, value):
        self[name] = value


class Enum(set):
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError


def get_object_or_none(klass, *args, **kwargs):
    queryset = _get_queryset(klass)
    try:
        return queryset.get(*args, **kwargs)
    except (queryset.model.DoesNotExist, ValueError):
        return None


def get_object_or_404(klass, *args, **kwargs):
    queryset = _get_queryset(klass)
    try:
        return queryset.get(*args, **kwargs)
    except (queryset.model.DoesNotExist, ValueError):
        raise Http404


def model_resources_to_dict():
    from resource import resource_tracker

    model_resources = {}
    for resource in resource_tracker:
        if hasattr(resource, 'model') and issubclass(resource.model, models.Model):
            model = resource.model
            model_label = lower('%s.%s' % (model._meta.app_label, model._meta.object_name))
            model_resources[model_label] = resource
    return model_resources


def set_rest_context_to_request(request, mapping):
    context = {}
    for key, (header_key, queryset_key) in mapping.items():
        val = request.GET.get(queryset_key, request.META.get(header_key))
        if val:
            context[key] = val
    request._rest_context = context
