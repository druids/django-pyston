from __future__ import unicode_literals

import re
import warnings

import six

from six.moves import reduce
from six.moves.urllib.parse import urlparse

from django.conf import settings as django_settings
from django.http.response import HttpResponse, HttpResponseBase
from django.utils.decorators import classonlymethod
from django.utils.encoding import force_text
from django.db.models.base import Model
from django.db.models.query import QuerySet
from django.db.models.fields import DateTimeField
from django.http.response import Http404
from django.forms.models import modelform_factory
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _

from functools import update_wrapper

from chamber.shortcuts import get_object_or_none
from chamber.exceptions import PersistenceException
from chamber.utils import remove_accent
from chamber.utils import transaction

from pyston.conf import settings
from pyston.utils.helpers import serialized_data_to_python
from pyston.forms import ISODateTimeField

from .paginator import Paginator
from .response import (HeadersResponse, RESTCreatedResponse, RESTNoContentResponse, ResponseErrorFactory,
                       ResponseExceptionFactory)
from .exception import (RESTException, ConflictException, NotAllowedException, DataInvalidException,
                        ResourceNotFoundException, NotAllowedMethodException, DuplicateEntryException,
                        UnsupportedMediaTypeException, MimerDataException)
from .forms import RESTModelForm
from .utils import coerce_rest_request_method, set_rest_context_to_request, RFS, rfs
from .utils.helpers import str_to_class
from .serializer import ResourceSerializer, ModelResourceSerializer, LazyMappedSerializedData, ObjectResourceSerializer
from .converters import get_converter_name_from_request, get_converter_from_request, get_converter


ACCESS_CONTROL_ALLOW_ORIGIN = 'Access-Control-Allow-Origin'
ACCESS_CONTROL_EXPOSE_HEADERS = 'Access-Control-Expose-Headers'
ACCESS_CONTROL_ALLOW_CREDENTIALS = 'Access-Control-Allow-Credentials'
ACCESS_CONTROL_ALLOW_HEADERS = 'Access-Control-Allow-Headers'
ACCESS_CONTROL_ALLOW_METHODS = 'Access-Control-Allow-Methods'
ACCESS_CONTROL_MAX_AGE = 'Access-Control-Max-Age'


typemapper = {}
resource_tracker = []


class ResourceMetaClass(type):
    """
    Metaclass that keeps a registry of class -> resource
    mappings.
    """
    def __new__(cls, name, bases, attrs):
        abstract = attrs.pop('abstract', False)
        new_cls = type.__new__(cls, name, bases, attrs)
        if not abstract and new_cls.register and settings.AUTO_REGISTER_RESOURCE:
            def already_registered(model):
                return typemapper.get(model)

            if hasattr(new_cls, 'model'):
                if already_registered(new_cls.model) and not settings.IGNORE_DUPE_MODELS:
                    warnings.warn('Resource already registered for model {}, '
                                  'you may experience inconsistent results.'.format(new_cls.model.__name__))

                typemapper[new_cls.model] = new_cls

            if name != 'BaseResource':
                resource_tracker.append(new_cls)

        return new_cls


class PermissionsResourceMixin(object):

    allowed_methods = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')

    def _get_via(self, via=None):
        via = list(via) if via is not None else []
        via.append(self)
        return via

    def get_allowed_methods(self, restricted_methods=None, **kwargs):
        allowed_methods = []

        tested_methods = set(self.allowed_methods)
        if restricted_methods is not None:
            tested_methods = tested_methods.intersection(restricted_methods)

        for method in tested_methods:
            try:
                self._check_permission(method, **kwargs)
                allowed_methods.append(method)
            except (NotImplementedError, NotAllowedException):
                pass
        return allowed_methods

    def _check_permission(self, name, *args, **kwargs):
        if not hasattr(self, 'has_{}_permission'.format(name)):
            if django_settings.DEBUG:
                raise NotImplementedError('Please implement method has_{}_permission to {}'.format(name, self.__class__))
            else:
                raise NotAllowedException

        if not getattr(self, 'has_{}_permission'.format(name))(*args, **kwargs):
            raise NotAllowedException

    def _check_call(self, name, *args, **kwargs):
        if not hasattr(self, 'has_{}_permission'.format(name)):
            if django_settings.DEBUG:
                raise NotImplementedError('Please implement method has_{}_permission to {}'.format(name, self.__class__))
            else:
                return False
        try:
            return getattr(self, 'has_{}_permission'.format(name))(*args, **kwargs)
        except Http404:
            return False

    def __getattr__(self, name):
        for regex, method in (
                (r'_check_(\w+)_permission', self._check_permission),
                (r'can_call_(\w+)', self._check_call)):
            m = re.match(regex, name)
            if m:
                def _call(*args, **kwargs):
                    return method(m.group(1), *args, **kwargs)
                return _call
        raise AttributeError('%r object has no attribute %r' % (self.__class__, name))

    def has_get_permission(self, **kwargs):
        return 'get' in self.allowed_methods and hasattr(self, 'get')

    def has_post_permission(self, **kwargs):
        return 'post' in self.allowed_methods and hasattr(self, 'post')

    def has_put_permission(self, **kwargs):
        return 'put' in self.allowed_methods and hasattr(self, 'put')

    def has_patch_permission(self, **kwargs):
        return 'patch' in self.allowed_methods and hasattr(self, 'patch')

    def has_delete_permission(self, **kwargs):
        return 'delete' in self.allowed_methods and hasattr(self, 'delete')

    def has_head_permission(self, **kwargs):
        return 'head' in self.allowed_methods and (hasattr(self, 'head') or self.has_get_permission(**kwargs))

    def has_options_permission(self, **kwargs):
        return 'options' in self.allowed_methods and hasattr(self, 'options')


class ObjectPermissionsResourceMixin(PermissionsResourceMixin):

    read_obj_permission = False
    create_obj_permission = False
    update_obj_permission = False
    delete_obj_permission = False

    def has_get_permission(self, **kwargs):
        return (
            super(ObjectPermissionsResourceMixin, self).has_get_permission(**kwargs) and
            self.has_read_obj_permission(**kwargs)
        )

    def has_post_permission(self, **kwargs):
        return (
            super(ObjectPermissionsResourceMixin, self).has_post_permission(**kwargs) and
            self.has_create_obj_permission(**kwargs)
        )

    def has_put_permission(self, **kwargs):
        return (
            super(ObjectPermissionsResourceMixin, self).has_put_permission(**kwargs) and
            self.has_update_obj_permission(**kwargs)
        )

    def has_patch_permission(self, **kwargs):
        return (
            super(ObjectPermissionsResourceMixin, self).has_patch_permission(**kwargs) and
            self.has_update_obj_permission(**kwargs)
        )

    def has_delete_permission(self, **kwargs):
        return (
            super(ObjectPermissionsResourceMixin, self).has_delete_permission(**kwargs) and
            self.has_delete_obj_permission(**kwargs)
        )

    def has_options_permission(self, **kwargs):
        return (
            super(ObjectPermissionsResourceMixin, self).has_options_permission(**kwargs) and
            self.has_read_obj_permission(**kwargs)
        )

    def has_read_obj_permission(self, obj=None, via=None):
        return self.read_obj_permission

    def has_create_obj_permission(self, obj=None, via=None):
        return self.create_obj_permission

    def has_update_obj_permission(self, obj=None, via=None):
        return self.update_obj_permission

    def has_delete_obj_permission(self, obj=None, via=None):
        return self.delete_obj_permission


class BaseResource(six.with_metaclass(ResourceMetaClass, PermissionsResourceMixin)):
    """
    BaseResource that gives you CRUD for free.
    You are supposed to subclass this for specific
    functionality.

    All CRUD methods (`read`/`update`/`create`/`delete`)
    receive a request as the first argument from the
    resource. Use this for checking `request.user`, etc.
    """

    allowed_methods = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')
    serializer = ResourceSerializer
    register = False
    abstract = True
    csrf_exempt = True
    cache = None
    paginator = Paginator
    resource_typemapper = {}

    DEFAULT_REST_CONTEXT_MAPPING = {
        'serialization_format': ('HTTP_X_SERIALIZATION_FORMAT', '_serialization_format'),
        'fields': ('HTTP_X_FIELDS', '_fields'),
        'offset': ('HTTP_X_OFFSET', '_offset'),
        'base': ('HTTP_X_BASE', '_base'),
        'accept': ('HTTP_ACCEPT', '_accept'),
        'content_type': ('CONTENT_TYPE', '_content_type'),
    }

    DATA_KEY_MAPPING = {}

    def __init__(self, request):
        self.request = request
        self.args = []
        self.kwargs = {}

    @property
    def exception_responses(self):
        errors_response_class = str_to_class(settings.ERRORS_RESPONSE_CLASS)
        error_response_class = str_to_class(settings.ERROR_RESPONSE_CLASS)
        return (
            (MimerDataException, ResponseErrorFactory(_('Bad Request'), 400, error_response_class)),
            (NotAllowedException, ResponseErrorFactory(_('Forbidden'), 403, error_response_class)),
            (UnsupportedMediaTypeException, ResponseErrorFactory(_('Unsupported Media Type'), 415,
                                                                 error_response_class)),
            (Http404, ResponseErrorFactory(_('Not Found'), 404, error_response_class)),
            (ResourceNotFoundException, ResponseErrorFactory(_('Not Found'), 404, error_response_class)),
            (NotAllowedMethodException, ResponseErrorFactory(_('Method Not Allowed'), 405, error_response_class)),
            (DuplicateEntryException, ResponseErrorFactory(_('Conflict/Duplicate'), 409, error_response_class)),
            (ConflictException, ResponseErrorFactory(_('Conflict/Duplicate'), 409, error_response_class)),
            (DataInvalidException, ResponseExceptionFactory(errors_response_class)),
            (RESTException, ResponseExceptionFactory(error_response_class)),
            (PersistenceException, ResponseExceptionFactory(error_response_class)),
        )

    @property
    def is_allowed_cors(self):
        return settings.CORS

    @property
    def cors_whitelist(self):
        return settings.CORS_WHITELIST

    @property
    def cors_max_age(self):
        return settings.CORS_MAX_AGE

    def _demap_key(self, lookup_key):
        return {v: k for k, v in self.DATA_KEY_MAPPING.items()}.get(lookup_key, lookup_key)

    def update_serialized_data(self, data):
        if data and self.DATA_KEY_MAPPING:
            data = LazyMappedSerializedData(data, self.DATA_KEY_MAPPING).serialize()
        return data

    def update_deserialized_data(self, data):
        return (
            {self._demap_key(k): v for k, v in data.items() if k not in self.DATA_KEY_MAPPING}
            if isinstance(data,dict) else {}
        )

    def get_dict_data(self):
        return self.update_deserialized_data(self.request.data if hasattr(self.request, 'data') else {})

    def _get_serialization_format(self):
        serialization_format = self.request._rest_context.get('serialization_format',
                                                              self.serializer.SERIALIZATION_TYPES.RAW)
        if serialization_format not in self.serializer.SERIALIZATION_TYPES:
            return self.serializer.SERIALIZATION_TYPES.RAW
        return serialization_format

    def head(self):
        return self.get()

    def _get_cors_allowed_headers(self):
        return ('X-Base', 'X-Offset', 'X-Fields', 'origin', 'content-type', 'accept')

    def _get_cors_allowed_exposed_headers(self):
        return ('X-Total', 'X-Serialization-Format-Options', 'X-Fields-Options')

    def _cors_is_origin_allowed(self, origin):
        if not origin:
            return False
        elif self.cors_whitelist == '__all__':
            return True
        else:
            url = urlparse(origin)
            return url.netloc in self.cors_whitelist or self._regex_domain_match(origin)

    def _regex_domain_match(self, origin):
        for domain_pattern in self.cors_whitelist:
            if re.match(domain_pattern, origin):
                return origin

    def _is_cors_options_request(self):
        return self.is_allowed_cors and self.request.META.get('HTTP_ORIGIN')

    def options(self):
        if self._is_cors_options_request():
            http_headers = {
                ACCESS_CONTROL_ALLOW_METHODS: self.request.META.get('HTTP_ACCESS_CONTROL_REQUEST_METHOD', 'OPTIONS'),
                ACCESS_CONTROL_ALLOW_HEADERS: ', '.join(self._get_cors_allowed_headers())
            }
            return HeadersResponse(None, http_headers=http_headers)
        else:
            return None

    def _get_converted_dict(self, result):
        return self._get_converted_serialized_data(result)

    def _get_converted_serialized_data(self, result):
        return self.serializer(self, request=self.request).serialize(
            result, self._get_serialization_format(), lazy=True
        )

    def _serialize(self, os, result, status_code, http_headers):
        try:
            converter = get_converter_from_request(self.request)
            http_headers['Content-Type'] = converter.content_type

            converter.encode_to_stream(os, self._get_converted_dict(result), resource=self, request=self.request,
                                       status_code=status_code, http_headers=http_headers, result=result)
        except ValueError:
            raise UnsupportedMediaTypeException

    def _deserialize(self):
        rm = self.request.method.upper()
        # Django's internal mechanism doesn't pick up
        # PUT request, so we trick it a little here.
        if rm in {'PUT', 'PATCH'}:
            coerce_rest_request_method(self.request)

        if rm in {'POST', 'PUT', 'PATCH'}:
            try:
                converter = get_converter_from_request(self.request, True)
                self.request.data = self.serializer(self).deserialize(converter.decode(force_text(self.request.body)))
            except (TypeError, ValueError):
                raise MimerDataException
            except NotImplementedError:
                raise UnsupportedMediaTypeException
        return self.request

    def _get_error_response_from_exception(self, exception):
        for exception_class, response_factory in self.exception_responses:
            if isinstance(exception, exception_class):
                return response_factory.get_response(exception)

    def _get_response_data(self):
        status_code = 200
        http_headers = {}

        fieldset = True
        try:
            self.request = self._deserialize()

            rm = self.request.method.lower()
            meth = getattr(self, rm, None)
            if not meth or rm not in self.allowed_methods:
                raise NotAllowedMethodException
            else:
                self._check_permission(rm)
                result = meth()
        except Exception as ex:
            result = self._get_error_response_from_exception(ex)
            if result is None:
                raise ex
            fieldset = False

        if isinstance(result, HeadersResponse):
            fieldset = result.fieldset
            http_headers = result.http_headers
            status_code = result.status_code
            result = result.result

        if isinstance(result, HttpResponse):
            status_code = result.status_code
            result = result._container
        return result, http_headers, status_code, fieldset

    def _set_response_headers(self, response, http_headers):
        for header, value in http_headers.items():
            response[header] = value

    def _get_from_cache(self):
        if self.cache:
            return self.cache.get_response(self.request)

    def _store_to_cache(self, response):
        if self.cache and response.status_code < 400:
            self.cache.cache_response(self.request, response)

    def _get_headers_queryset_context_mapping(self):
        return self.DEFAULT_REST_CONTEXT_MAPPING.copy()

    def _get_context(self):
        context = {}
        for key, (header_key, queryset_key) in self._get_headers_queryset_context_mapping().items():
            val = self.request.GET.get(queryset_key, self.request.META.get(header_key))
            if val:
                context[key] = val
        return context

    def render_response(self, result, http_headers, status_code, fieldset):
        if isinstance(result, HttpResponseBase):
            return result
        else:
            if not fieldset and 'fields' in self.request._rest_context:
                del self.request._rest_context['fields']
            response = HttpResponse()
            try:
                response.status_code = status_code
                http_headers = self._get_headers(http_headers)
                self._serialize(response, result, status_code, http_headers)
            except UnsupportedMediaTypeException:
                response.status_code = 415
                http_headers['Content-Type'] = self.request.get('HTTP_ACCEPT')

            self._set_response_headers(response, http_headers)
            return response

    def dispatch(self, request, *args, **kwargs):
        set_rest_context_to_request(request, self._get_headers_queryset_context_mapping())
        response = self._get_from_cache()
        if response:
            return response
        else:
            response = self.render_response(*self._get_response_data())
            self._store_to_cache(response)
            return response

    def get_name(self):
        return 'resource'

    def _get_filename(self):
        return '{}.{}'.format(self.get_name(), get_converter_name_from_request(self.request))

    def _get_allow_header(self):
        return ','.join((method.upper() for method in self.get_allowed_methods()))

    def _get_headers(self, default_http_headers):
        origin = self.request.META.get('HTTP_ORIGIN')

        http_headers = default_http_headers.copy()
        http_headers['X-Serialization-Format-Options'] = ','.join(self.serializer.SERIALIZATION_TYPES)
        http_headers['Cache-Control'] = 'private, no-cache, no-store, max-age=0'
        http_headers['Pragma'] = 'no-cache'
        http_headers['Expires'] = '0'
        http_headers['Content-Disposition'] = 'inline; filename="{}"'.format(self._get_filename())
        http_headers['Allow'] = self._get_allow_header()
        http_headers['Vary'] = 'Accept'

        if self.is_allowed_cors:
            if origin and self._cors_is_origin_allowed(origin):
                http_headers[ACCESS_CONTROL_ALLOW_ORIGIN] = origin
            http_headers[ACCESS_CONTROL_ALLOW_CREDENTIALS] = (
                'true' if settings.CORS_ALLOW_CREDENTIALS else 'false'
            )
            cors_allowed_exposed_headers = self._get_cors_allowed_exposed_headers()
            if cors_allowed_exposed_headers:
                http_headers[ACCESS_CONTROL_EXPOSE_HEADERS] = ', '.join(cors_allowed_exposed_headers)
            http_headers[ACCESS_CONTROL_MAX_AGE] = str(self.cors_max_age)
        return http_headers

    @classonlymethod
    def as_view(cls, allowed_methods=None, **initkwargs):
        def view(request, *args, **kwargs):
            self = cls(request, **initkwargs)
            self.request = request
            self.args = args
            self.kwargs = kwargs
            if allowed_methods is not None:
                self.allowed_methods = set(allowed_methods) & set(cls.allowed_methods)
            else:
                self.allowed_methods = set(cls.allowed_methods)
            return self.dispatch(request, *args, **kwargs)
        view.csrf_exempt = cls.csrf_exempt

        # take name and docstring from class
        update_wrapper(view, cls, updated=())

        # and possible attributes set by decorators
        # like csrf_exempt from dispatch
        update_wrapper(view, cls.dispatch, assigned=())
        return view


def join_rfs(*iterable):
    return reduce(lambda a, b: a.join(b), iterable, rfs())


class DefaultRESTObjectResource(ObjectPermissionsResourceMixin):

    fields = None
    allowed_fields = None
    detailed_fields = None
    general_fields = None
    guest_fields = None
    allowed_methods = None
    default_fields = None
    extra_fields = None

    def get_allowed_fields_rfs(self, obj=None):
        return rfs(self.allowed_fields) if self.allowed_fields is not None else join_rfs(
            self.get_fields_rfs(obj),
            self.get_detailed_fields_rfs(obj),
            self.get_general_fields_rfs(obj),
            self.get_extra_fields_rfs(obj),
            self.get_default_fields_rfs(obj)
        )

    def get_fields(self, obj=None):
        return list(self.fields) if self.fields is not None else None

    def get_default_fields(self, obj=None):
        return list(self.default_fields) if self.default_fields is not None else None

    def get_detailed_fields(self, obj=None):
        return list(self.detailed_fields) if self.detailed_fields is not None else self.get_fields(obj=obj)

    def get_general_fields(self, obj=None):
        return list(self.general_fields) if self.general_fields is not None else self.get_fields(obj=obj)

    def get_guest_fields(self, obj=None):
        return list(self.guest_fields) if self.guest_fields is not None else None

    def get_extra_fields(self, obj=None):
        return list(self.extra_fields) if self.extra_fields is not None else None

    def get_fields_rfs(self, obj=None):
        fields = self.get_fields(obj=obj)

        return rfs(fields) if fields is not None else rfs()

    def get_default_fields_rfs(self, obj=None):
        default_fields = self.get_default_fields(obj=obj)

        return rfs(default_fields) if default_fields is not None else rfs()

    def get_detailed_fields_rfs(self, obj=None):
        detailed_fields = self.get_detailed_fields(obj=obj)

        return (rfs(detailed_fields) if detailed_fields is not None else rfs()).join(self.get_default_fields_rfs())

    def get_general_fields_rfs(self, obj=None):
        general_fields = self.get_general_fields(obj=obj)

        return (rfs(general_fields) if general_fields is not None else rfs()).join(self.get_default_fields_rfs())

    def get_guest_fields_rfs(self, obj=None):
        guest_fields = self.get_guest_fields(obj=obj)

        return rfs(guest_fields) if guest_fields is not None else rfs()

    def get_extra_fields_rfs(self, obj=None):
        extra_fields = self.get_extra_fields(obj=obj)

        return rfs(extra_fields) if extra_fields is not None else rfs()


class DefaultRESTModelResource(DefaultRESTObjectResource):

    allowed_methods = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')
    model = None

    def get_detailed_fields(self, obj=None):
        detailed_fields = super(DefaultRESTModelResource, self).get_detailed_fields(obj=obj)
        return list(self.model._rest_meta.detailed_fields) if detailed_fields is None else detailed_fields

    def get_general_fields(self, obj=None):
        general_fields = super(DefaultRESTModelResource, self).get_general_fields(obj=obj)
        return list(self.model._rest_meta.general_fields) if general_fields is None else general_fields

    def get_guest_fields(self, obj=None):
        guest_fields = super(DefaultRESTModelResource, self).get_guest_fields(obj=obj)
        return list(self.model._rest_meta.guest_fields) if guest_fields is None else guest_fields

    def get_extra_fields(self, obj=None):
        extra_fields = super(DefaultRESTModelResource, self).get_extra_fields(obj=obj)
        return list(self.model._rest_meta.extra_fields) if extra_fields is None else extra_fields

    def get_default_fields(self, obj=None):
        default_fields = super(DefaultRESTModelResource, self).get_default_fields(obj=obj)
        return list(self.model._rest_meta.default_fields) if default_fields is None else default_fields


class BaseObjectResource(DefaultRESTObjectResource, BaseResource):

    allowed_methods = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')
    pk_name = 'pk'
    pk_field_name = 'id'
    abstract = True
    partial_put_update = None
    partial_related_update = None
    serializer = ObjectResourceSerializer

    def _serialize(self, os, result, status_code, http_headers):
        try:
            converter = get_converter_from_request(self.request)
            http_headers['Content-Type'] = converter.content_type

            converter.encode_to_stream(os, self._get_converted_dict(result), resource=self, request=self.request,
                                       status_code=status_code, http_headers=http_headers, result=result,
                                       requested_fields=self._get_requested_fieldset(result))
        except ValueError:
            raise UnsupportedMediaTypeException

    def _get_converted_serialized_data(self, result):
        return self.serializer(self, request=self.request).serialize(
            result, self._get_serialization_format(), requested_fieldset=self._get_requested_fieldset(result),
            lazy=True
        )

    def _get_requested_fieldset(self, result):
        requested_fields = self.request._rest_context.get('fields')
        if requested_fields:
            return RFS.create_from_string(requested_fields)
        elif isinstance(result, Model):
            return self.get_detailed_fields_rfs(obj=result)
        elif isinstance(result, QuerySet):
            return self.get_general_fields_rfs()
        else:
            return None

    def _get_obj_or_404(self, pk=None):
        obj = self._get_obj_or_none(pk)
        if not obj:
            raise Http404
        return obj

    def render_response(self, result, http_headers, status_code, fieldset):
        return super(BaseObjectResource, self).render_response(result, http_headers, status_code, fieldset)

    def _get_allowed_fields_options_header(self):
        return ','.join(self.get_allowed_fields_rfs(self._get_obj_or_none()).flat())

    def _get_allow_header(self):
        return ','.join((method.upper() for method in self.get_allowed_methods(obj=self._get_obj_or_none())))

    def _get_headers(self, default_http_headers):
        http_headers = super(BaseObjectResource, self)._get_headers(default_http_headers)
        http_headers['X-Fields-Options'] = self._get_allowed_fields_options_header()
        return http_headers

    def _get_queryset(self):
        """
        Should return list or db queryset
        """
        raise NotImplementedError

    def _get_obj_or_none(self, pk=None):
        """
        Should return one object
        """
        raise NotImplementedError

    def _filter_queryset(self, qs):
        """
        Should contain implementation for objects filtering
        """
        return qs

    def _preload_queryset(self, qs):
        """
        May contain preloading implementation for queryset
        """
        return qs

    def _order_queryset(self, qs):
        """
        Should contain implementation for objects ordering
        """
        return qs

    def _exists_obj(self, **kwargs):
        """
        Should return true if object exists
        """
        raise NotImplementedError

    def _get_pk(self):
        return self.kwargs.get(self.pk_name)

    def post(self):
        pk = self._get_pk()
        data = self.get_dict_data()
        if pk and self._exists_obj(pk=pk):
            raise DuplicateEntryException
        return RESTCreatedResponse(self.atomic_create_or_update(data))

    def get(self):
        pk = self._get_pk()
        if pk:
            return self._get_obj_or_404(pk=pk)
        qs = self._preload_queryset(self._get_queryset().all())
        qs = self._filter_queryset(qs)
        qs = self._order_queryset(qs)
        paginator = self.paginator(qs, self.request)
        return HeadersResponse(paginator.page_qs, paginator.headers)

    def put(self):
        pk = self._get_pk()
        data = self.get_dict_data()
        obj = self._get_obj_or_404(pk=pk)
        data[self.pk_field_name] = obj.pk
        try:
            # Backward compatibility
            partial_update = settings.PARTIAL_PUT_UPDATE if self.partial_put_update is None else self.partial_put_update
            return self.atomic_create_or_update(data, partial_update=partial_update)
        except ConflictException:
            # If object allready exists and user doesn't have permissions to change it should be returned 404 (the same
            # response as for GET method)
            raise Http404

    def patch(self):
        pk = self._get_pk()
        data = self.get_dict_data()
        obj = self._get_obj_or_404(pk=pk)
        data[self.pk_field_name] = obj.pk
        try:
            return self.atomic_create_or_update(data, partial_update=True)
        except ConflictException:
            # If object allready exists and user doesn't have permissions to change it should be returned 404 (the same
            # response as for GET method)
            raise Http404

    def delete(self):
        pk = self.kwargs.get(self.pk_name)
        self.delete_obj_with_pk(pk)
        return RESTNoContentResponse()

    def delete_obj_with_pk(self, pk, via=None):
        via = via or []
        obj = self._get_obj_or_404(pk)
        self._check_delete_obj_permission(obj=obj, via=via)
        self._pre_delete_obj(obj)
        self._delete_obj(obj)
        self._post_delete_obj(obj)

    def _pre_delete_obj(self, obj):
        pass

    def _delete_obj(self, obj):
        raise NotImplementedError

    def _post_delete_obj(self, obj):
        pass

    @transaction.atomic
    def atomic_create_or_update(self, data, partial_update=False):
        """
        Atomic object creation
        """
        return self.create_or_update(data, partial_update=partial_update)

    def _get_instance(self, data):
        """
        Should contains implementation for get object according to input data values
        """
        raise NotImplementedError

    def _generate_form_class(self, inst, exclude=None):
        return self.form_class

    def _get_form(self, fields=None, inst=None, data=None, files=None, initial=None, partial_update=False):
        # When is send PUT (resource instance exists), it is possible send only changed values.
        initial = {} if initial is None else initial
        exclude = []

        kwargs = self._get_form_kwargs()
        if inst:
            kwargs['instance'] = inst
        if data is not None:
            kwargs['data'] = data
            kwargs['files'] = files

        form_class = self._generate_form_class(inst, exclude)
        return form_class(initial=initial, partial_update=partial_update, **kwargs)

    def _get_form_kwargs(self):
        return {}

    def _get_form_initial(self, obj):
        return {}

    def _can_save_obj(self, change, obj, form, via):
        if change and (not via or form.has_changed()):
            self._check_update_obj_permission(obj=obj, via=via)
        elif not change:
            self._check_create_obj_permission(obj=obj, via=via)

        return not change or self.has_update_obj_permission(obj=obj, via=via)

    def create_or_update(self, data, via=None, partial_update=False):
        try:
            return self._create_or_update(data, via, partial_update=partial_update)
        except DataInvalidException as ex:
            raise DataInvalidException(self.update_serialized_data(ex.errors))

    def _create_or_update(self, data, via=None, partial_update=False):
        """
        Helper for creating or updating resource
        """
        from pyston.data_processor import data_preprocessors, data_postprocessors

        via = [] if via is None else via
        inst = self._get_instance(data)
        change = inst and True or False

        files = self.request.FILES.copy()

        form = self._get_form(inst=inst, data=data, initial=self._get_form_initial(inst))

        # Backward compatibility
        partial_related_update = (
            settings.PARTIAL_RELATED_UPDATE if self.partial_related_update is None else self.partial_related_update
        ) or partial_update

        for preprocessor in data_preprocessors.get_processors(type(self)):
            data, files = preprocessor(self, form, inst, via, partial_related_update).process_data(data, files)

        form = self._get_form(fields=form.fields.keys(), inst=inst, data=data, files=files,
                              initial=self._get_form_initial(inst), partial_update=partial_update)

        errors = form.is_invalid()
        if errors:
            raise DataInvalidException(errors)

        inst = form.save(commit=False)

        can_save_obj = self._can_save_obj(change, inst, form, via)
        if can_save_obj:
            self._pre_save_obj(inst, form, change)
            self._save_obj(inst, form, change)

        if inst.pk:
            for preprocessor in data_postprocessors.get_processors(type(self)):
                data, files = preprocessor(self, form, inst, via, partial_related_update).process_data(data, files)

        if can_save_obj:
            if hasattr(form, 'save_m2m'):
                form.save_m2m()
            self._post_save_obj(inst, form, change)
        return inst

    def _pre_save_obj(self, obj, form, change):
        pass

    def _save_obj(self, obj, form, change):
        raise NotImplementedError

    def _post_save_obj(self, obj, form, change):
        pass


class BaseModelResource(DefaultRESTModelResource, BaseObjectResource):

    register = True
    abstract = True
    form_class = RESTModelForm
    serializer = ModelResourceSerializer
    form_fields = None

    def _get_queryset(self):
        return self.model.objects.all()

    def _get_obj_or_none(self, pk=None):
        if pk or self._get_pk():
            return get_object_or_none(self._get_queryset(), pk=(pk or self._get_pk()))
        else:
            return None

    def _exists_obj(self, **kwargs):
        return self.model.objects.filter(**kwargs).exists()

    def _delete_obj(self, obj):
        obj.delete()

    def _save_obj(self, obj, form, change):
        obj.save()

    def _get_exclude(self, obj=None):
        return []

    def _get_form_class(self, inst):
        return self.form_class

    def get_name(self):
        return force_text(remove_accent(force_text(self.model._meta.verbose_name_plural)))

    def formfield_for_dbfield(self, db_field, **kwargs):
        if isinstance(db_field, DateTimeField):
            kwargs.update({'form_class': ISODateTimeField})
        return db_field.formfield(**kwargs)

    def _get_instance(self, data):
        # If data contains id this method is update otherwise create
        inst = None
        pk = data.get(self.pk_field_name)
        if pk:
            try:
                try:
                    inst = self._get_queryset().get(pk=pk)
                except (ObjectDoesNotExist, ValueError):
                    if self.model.objects.filter(pk=pk).exists():
                        raise ConflictException
            except ValueError:
                pass
        return inst

    def _get_form_fields(self, obj=None):
        return self.form_fields

    def _generate_form_class(self, inst, exclude=None):
        exclude = [] if exclude is None else exclude
        exclude = list(self._get_exclude(inst)) + exclude
        form_class = self._get_form_class(inst)
        fields = self._get_form_fields(inst)
        if hasattr(form_class, '_meta') and form_class._meta.exclude:
            exclude.extend(form_class._meta.exclude)
        return modelform_factory(self.model, form=form_class, exclude=exclude, fields=fields,
                                 formfield_callback=self.formfield_for_dbfield)
