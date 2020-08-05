import re
import warnings

from functools import reduce

from urllib.parse import urlparse

from collections import OrderedDict

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.http.response import HttpResponse, HttpResponseBase
from django.utils.decorators import classonlymethod
from django.utils.encoding import force_text
from django.db.models.base import Model
from django.db.models.query import QuerySet
from django.db.models.fields import DateTimeField
from django.http.response import Http404
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from django.utils.module_loading import import_string

from functools import update_wrapper

from chamber.shortcuts import get_object_or_none
from chamber.utils import remove_accent, transaction

from .conf import settings
from .paginator import BaseOffsetPaginator
from .response import (HeadersResponse, RESTCreatedResponse, RESTNoContentResponse, ResponseErrorFactory,
                       ResponseExceptionFactory, ResponseValidationExceptionFactory)
from .exception import (RESTException, ConflictException, NotAllowedException, DataInvalidException,
                        ResourceNotFoundException, NotAllowedMethodException, DuplicateEntryException,
                        UnsupportedMediaTypeException, MimerDataException, UnauthorizedException,
                        UnprocessableEntity)
from .forms import ISODateTimeField, RESTModelForm, rest_modelform_factory, RESTValidationError
from .utils import coerce_rest_request_method, set_rest_context_to_request, RFS, rfs
from .utils.helpers import str_to_class
from .serializer import (
    ResourceSerializer, ModelResourceSerializer, LazyMappedSerializedData, ObjectResourceSerializer, SerializableObj
)
from .converters import get_converter_name_from_request, get_converter_from_request
from .filters.managers import MultipleFilterManager
from .order.managers import DefaultModelOrderManager
from .requested_fields.managers import DefaultRequestedFieldsManager


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

        if not abstract:
            converters = OrderedDict()
            for converter_class_path in new_cls.converter_classes:
                converter_class = (
                    import_string(converter_class_path) if isinstance(converter_class_path, str)
                    else converter_class_path
                )
                converters[converter_class.format] = converter_class()
            new_cls.converters = converters
        return new_cls


class PermissionsResourceMixin:

    allowed_methods = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')

    def get_allowed_methods(self):
        return set(self.allowed_methods)

    def _get_via(self, via=None):
        via = list(via) if via is not None else []
        via.append(self)
        return via

    def check_permissions_and_get_allowed_methods(self, restricted_methods=None, **kwargs):
        allowed_methods = []

        tested_methods = self.get_allowed_methods()
        if restricted_methods is not None:
            tested_methods = tested_methods.intersection(restricted_methods)

        for method in tested_methods:
            try:
                self._check_permission(method, **kwargs)
                allowed_methods.append(method)
            except (NotImplementedError, NotAllowedException, UnauthorizedException):
                pass
        return allowed_methods

    def _check_permission(self, name=None, *args, **kwargs):
        name = name or self.request.method.lower()

        if not hasattr(self, 'has_{}_permission'.format(name)):
            if django_settings.DEBUG:
                raise NotImplementedError('Please implement method has_{}_permission to {}'.format(name, self.__class__))
            else:
                raise NotAllowedException

        if not getattr(self, 'has_{}_permission'.format(name))(*args, **kwargs):
            raise NotAllowedException

    def has_permission(self, name=None, *args, **kwargs):
        name = name or self.request.method.lower()

        if not hasattr(self, 'has_{}_permission'.format(name)):
            if django_settings.DEBUG:
                raise NotImplementedError('Please implement method has_{}_permission to {}'.format(name, self.__class__))
            else:
                return False
        try:
            return getattr(self, 'has_{}_permission'.format(name))(*args, **kwargs)
        except Http404:
            return False

    def has_get_permission(self, **kwargs):
        return 'get' in self.get_allowed_methods() and hasattr(self, 'get')

    def has_post_permission(self, **kwargs):
        return 'post' in self.get_allowed_methods() and hasattr(self, 'post')

    def has_put_permission(self, **kwargs):
        return 'put' in self.get_allowed_methods() and hasattr(self, 'put')

    def has_patch_permission(self, **kwargs):
        return 'patch' in self.get_allowed_methods() and hasattr(self, 'patch')

    def has_delete_permission(self, **kwargs):
        return 'delete' in self.get_allowed_methods() and hasattr(self, 'delete')

    def has_head_permission(self, **kwargs):
        return 'head' in self.get_allowed_methods() and (hasattr(self, 'head') or self.has_get_permission(**kwargs))

    def has_options_permission(self, **kwargs):
        return 'options' in self.get_allowed_methods() and hasattr(self, 'options')


class ObjectPermissionsResourceMixin(PermissionsResourceMixin):

    can_create_obj = False
    can_read_obj = False
    can_update_obj = False
    can_delete_obj = False

    def has_create_obj_permission(self, obj=None, via=None):
        return self.can_create_obj

    def has_read_obj_permission(self, obj=None, via=None):
        return self.can_read_obj

    def has_update_obj_permission(self, obj=None, via=None):
        return self.can_update_obj

    def has_delete_obj_permission(self, obj=None, via=None):
        return self.can_delete_obj


class BaseResource(PermissionsResourceMixin, metaclass=ResourceMetaClass):
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
    paginator = BaseOffsetPaginator
    resource_typemapper = {}
    converter_classes = settings.CONVERTERS
    errors_response_class = settings.ERRORS_RESPONSE_CLASS
    error_response_class = settings.ERROR_RESPONSE_CLASS
    field_labels = {}
    requested_fields_manager = DefaultRequestedFieldsManager()
    renamed_fields = {}

    DEFAULT_REST_CONTEXT_MAPPING = {
        'serialization_format': ('HTTP_X_SERIALIZATION_FORMAT', '_serialization_format'),
        'fields': ('HTTP_X_FIELDS', '_fields'),
        'offset': ('HTTP_X_OFFSET', '_offset'),
        'base': ('HTTP_X_BASE', '_base'),
        'accept': ('HTTP_ACCEPT', '_accept'),
        'content_type': ('CONTENT_TYPE', '_content_type'),
        'filter': ('HTTP_X_FILTER', 'filter'),
        'order': ('HTTP_X_ORDER', 'order'),
    }

    def update_errors(self, data):
        if data and self.renamed_fields:
            data = LazyMappedSerializedData(data, {v: k for k, v in self.renamed_fields.items()}).serialize()
        return data

    def update_data(self, data):
        if data and isinstance(data, dict) and self.renamed_fields:
            return {self.renamed_fields.get(k, k): v for k, v in data.items()}
        else:
            return data

    def __init__(self, request):
        self.request = request
        self.args = []
        self.kwargs = {}

    def _get_requested_fieldset(self, result):
        if self.requested_fields_manager:
            requested_fields = self.requested_fields_manager.get_requested_fields(self, self.request)
            if requested_fields is not None:
                return requested_fields

        return None

    def get_field_labels(self):
        return self.field_labels

    def get_allowed_methods(self):
        allowed_methods = super().get_allowed_methods()
        if self.is_allowed_cors:
            allowed_methods.add('options')
        return allowed_methods

    @property
    def exception_responses(self):
        errors_response_class = (
            str_to_class(self.errors_response_class) if isinstance(self.errors_response_class, str)
            else self.errors_response_class
        )
        error_response_class = (
            str_to_class(self.error_response_class) if isinstance(self.error_response_class, str)
            else self.error_response_class
        )
        return (
            (MimerDataException, ResponseErrorFactory(_('Bad Request'), 400, error_response_class)),
            (UnauthorizedException, ResponseErrorFactory(_('Unauthorized'), 401, error_response_class)),
            (NotAllowedException, ResponseErrorFactory(_('Forbidden'), 403, error_response_class)),
            (UnsupportedMediaTypeException, ResponseErrorFactory(_('Unsupported Media Type'), 415,
                                                                 error_response_class)),
            (Http404, ResponseErrorFactory(_('Not Found'), 404, error_response_class)),
            (ResourceNotFoundException, ResponseErrorFactory(_('Not Found'), 404, error_response_class)),
            (NotAllowedMethodException, ResponseErrorFactory(_('Method Not Allowed'), 405, error_response_class)),
            (DuplicateEntryException, ResponseErrorFactory(_('Conflict/Duplicate'), 409, error_response_class)),
            (ConflictException, ResponseErrorFactory(_('Conflict/Duplicate'), 409, error_response_class)),
            (DataInvalidException, ResponseExceptionFactory(errors_response_class)),
            (UnprocessableEntity, ResponseExceptionFactory(error_response_class, code=422)),
            (RESTException, ResponseExceptionFactory(error_response_class)),
            (ValidationError, ResponseValidationExceptionFactory(error_response_class)),
            (RESTValidationError, ResponseValidationExceptionFactory(error_response_class)),
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

    def get_dict_data(self):
        return self.update_data(
            self.request.data if hasattr(self.request, 'data') and isinstance(self.request.data, dict) else {}
        )

    def _get_serialization_format(self):
        serialization_format = self.request._rest_context.get('serialization_format',
                                                              self.serializer.SERIALIZATION_TYPES.RAW)
        if serialization_format not in self.serializer.SERIALIZATION_TYPES:
            return self.serializer.SERIALIZATION_TYPES.RAW
        return serialization_format

    def head(self):
        return self.get()

    def _get_cors_allowed_headers(self):
        return settings.CORS_ALLOWED_HEADERS

    def _get_cors_allowed_exposed_headers(self):
        return settings.CORS_ALLOWED_EXPOSED_HEADERS

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
        return (
            self.is_allowed_cors and self.request.method.upper() == 'OPTIONS' and self.request.META.get('HTTP_ORIGIN')
        )

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
            result, self._get_serialization_format(), lazy=True, allow_tags=self._get_converter().allow_tags,
            requested_fieldset=self._get_requested_fieldset(result)
        )

    def _get_converter(self):
        try:
            return get_converter_from_request(self.request, self.converters)
        except ValueError:
            raise UnsupportedMediaTypeException

    def _serialize(self, output_stream, result, status_code, http_headers):
        converter = self._get_converter()
        http_headers['Content-Type'] = converter.content_type
        converter.encode_to_stream(
            output_stream, self._get_converted_dict(result), resource=self, request=self.request,
            status_code=status_code, http_headers=http_headers, result=result,
            requested_fieldset=self._get_requested_fieldset(result)
        )

    def _deserialize(self):
        rm = self.request.method.upper()
        # Django's internal mechanism doesn't pick up
        # PUT request, so we trick it a little here.
        if rm in {'PUT', 'PATCH'}:
            coerce_rest_request_method(self.request)

        if rm in {'POST', 'PUT', 'PATCH'}:
            try:
                converter = get_converter_from_request(self.request, self.converters, True)
                self.request.data = self.serializer(self).deserialize(
                    converter.decode(force_text(self.request.body), resource=self)
                )
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
            rm = self.request.method.lower()
            meth = getattr(self, rm, None)

            if not meth or rm not in self.get_allowed_methods():
                raise NotAllowedMethodException

            self.request = self._deserialize()
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
            if not fieldset:
                self.request._rest_context.pop('fields', None)
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

    def _get_name(self):
        return 'resource'

    def _get_filename(self):
        return '{}.{}'.format(self._get_name(), get_converter_name_from_request(self.request, self.converters))

    def _get_allow_header(self):
        return ','.join((method.upper() for method in self.check_permissions_and_get_allowed_methods()))

    def _get_headers(self, default_http_headers):
        origin = self.request.META.get('HTTP_ORIGIN')

        http_headers = default_http_headers.copy()
        http_headers['Cache-Control'] = 'private, no-cache, no-store, max-age=0'
        http_headers['Pragma'] = 'no-cache'
        http_headers['Expires'] = '0'
        http_headers['Vary'] = 'Accept'

        if self.has_permission():
            http_headers['X-Serialization-Format-Options'] = ','.join(self.serializer.SERIALIZATION_TYPES)
            http_headers['Content-Disposition'] = 'inline; filename="{}"'.format(self._get_filename())
            http_headers['Allow'] = self._get_allow_header()

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
    filter_fields = None
    extra_filter_fields = None
    order_fields = None
    extra_order_fields = None

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

    def get_extra_filter_fields(self):
        """
        :return: filter fields list that excludes default filter fields.
        """
        return list(self.extra_filter_fields) if self.extra_filter_fields is not None else None

    def get_filter_fields(self):
        """
        :return: filter fields list or None.
        """
        return list(self.filter_fields) if self.filter_fields is not None else None

    def get_filter_fields_rfs(self):
        """
        :return: RFS of allowed filter fields. If filter_fields is None value is returned from all allowed fields to
        read.
        """
        filter_fields = self.get_filter_fields()
        extra_filter_fields = self.get_extra_filter_fields() or ()
        if filter_fields is None:
            return rfs(extra_filter_fields).join(self.get_allowed_fields_rfs())
        else:
            return rfs(extra_filter_fields).join(rfs(filter_fields))

    def get_extra_order_fields(self):
        """
        :return: order fields list that excludes default filter fields.
        """
        return list(self.extra_order_fields) if self.extra_order_fields is not None else None

    def get_order_fields(self):
        """
        :return: order fields list or None.
        """
        return list(self.order_fields) if self.order_fields is not None else None

    def get_order_fields_rfs(self):
        """
        :return: RFS of allowed order fields. If order_fields is None value is returned from all allowed fields to
        read.
        """
        order_fields = self.get_order_fields()
        extra_order_fields = self.get_extra_order_fields() or ()
        if order_fields is None:
            return rfs(extra_order_fields).join(self.get_allowed_fields_rfs())
        else:
            return rfs(extra_order_fields).join(rfs(order_fields))

    def get_methods_returning_field_value(self, fields):
        """
        Returns dict of resource methods which can be used with serializer to get a field value.
        :param fields: list of field names
        :return: dict of resource methods. Key is a field name, value is a method that returns field value.
        """
        method_fields = {}
        for method_name in fields:
            real_method_name = self.renamed_fields.get(method_name, method_name)
            method = self.get_method_returning_field_value(real_method_name)
            if method:
                method_fields[real_method_name] = method
        return method_fields

    def get_method_returning_field_value(self, field_name):
        """
        Returns method which can be used with serializer to get a field value.
        :param field_name: name of th field
        :return: resource method
        """
        method = getattr(self, field_name, None)
        return method if method and callable(method) else None


class DefaultRESTModelResource(DefaultRESTObjectResource):

    allowed_methods = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')
    model = None

    def get_detailed_fields(self, obj=None):
        detailed_fields = super().get_detailed_fields(obj=obj)
        return list(self.model._rest_meta.detailed_fields) if detailed_fields is None else detailed_fields

    def get_general_fields(self, obj=None):
        general_fields = super().get_general_fields(obj=obj)
        return list(self.model._rest_meta.general_fields) if general_fields is None else general_fields

    def get_guest_fields(self, obj=None):
        guest_fields = super().get_guest_fields(obj=obj)
        return list(self.model._rest_meta.guest_fields) if guest_fields is None else guest_fields

    def get_extra_fields(self, obj=None):
        extra_fields = super().get_extra_fields(obj=obj)
        return list(self.model._rest_meta.extra_fields) if extra_fields is None else extra_fields

    def get_default_fields(self, obj=None):
        default_fields = super().get_default_fields(obj=obj)
        return list(self.model._rest_meta.default_fields) if default_fields is None else default_fields

    def get_extra_filter_fields(self):
        extra_filter_fields = super().get_extra_filter_fields()
        return list(self.model._rest_meta.extra_filter_fields) if extra_filter_fields is None else extra_filter_fields

    def get_filter_fields(self):
        filter_fields = super().get_filter_fields()
        return self.model._rest_meta.filter_fields if filter_fields is None else filter_fields

    def get_extra_order_fields(self):
        extra_order_fields = super().get_extra_order_fields()
        return list(self.model._rest_meta.extra_order_fields) if extra_order_fields is None else extra_order_fields

    def get_order_fields(self):
        order_fields = super().get_order_fields()
        return self.model._rest_meta.order_fields if order_fields is None else order_fields


class BaseObjectResource(DefaultRESTObjectResource, BaseResource):

    allowed_methods = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')
    pk_name = 'pk'
    pk_field_name = 'id'
    abstract = True
    partial_put_update = None
    partial_related_update = None
    serializer = ObjectResourceSerializer

    def _serialize(self, output_stream, result, status_code, http_headers):
        try:
            converter = get_converter_from_request(self.request, self.converters)
            http_headers['Content-Type'] = converter.content_type

            converter.encode_to_stream(
                output_stream, self._get_converted_dict(result), resource=self, request=self.request,
                status_code=status_code, http_headers=http_headers, result=result,
                requested_fields=self._get_requested_fieldset(result)
            )
        except ValueError:
            raise UnsupportedMediaTypeException

    def _get_converted_serialized_data(self, result):
        return self.serializer(self, request=self.request).serialize(
            result, self._get_serialization_format(), requested_fieldset=self._get_requested_fieldset(result),
            lazy=True, allow_tags=self._get_converter().allow_tags
        )

    def _get_obj_or_404(self, pk=None):
        obj = self._get_obj_or_none(pk)
        if not obj:
            raise Http404
        return obj

    def render_response(self, result, http_headers, status_code, fieldset):
        return super(BaseObjectResource, self).render_response(result, http_headers, status_code, fieldset)

    def _get_allow_header(self):
        return ','.join((
            method.upper() for method in self.check_permissions_and_get_allowed_methods(obj=self._get_obj_or_none())
        ))

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
        qs = self._preload_queryset(self._get_queryset())
        qs = self._filter_queryset(qs)
        qs = self._order_queryset(qs)
        if self.paginator:
            paginator = self.paginator(qs, self.request)
            return HeadersResponse(paginator.page_qs, paginator.headers)
        else:
            return qs

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
        self._check_permission('delete_obj', obj=obj, via=via)
        self._pre_delete_obj(obj)
        self._delete_obj(obj)
        self._post_delete_obj(obj)

    def _pre_delete_obj(self, obj):
        pass

    def _delete_obj(self, obj):
        raise NotImplementedError

    def _post_delete_obj(self, obj):
        pass

    @transaction.atomic_with_signals
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
            self._check_permission('update_obj', obj=obj, via=via)
        elif not change:
            self._check_permission('create_obj', obj=obj, via=via)

        return not change or self.has_update_obj_permission(obj=obj, via=via)

    def create_or_update(self, data, via=None, partial_update=False):
        try:
            return self._create_or_update(data, via, partial_update=partial_update)
        except DataInvalidException as ex:
            raise DataInvalidException(self.update_errors(ex.errors))

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
            if hasattr(form, 'post_save'):
                form.post_save()

            # Because reverse related validations is performed after save errors check must be evaluated two times
            errors = form.is_invalid()
            if errors:
                raise DataInvalidException(errors)

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

    filters = {}
    filter_manager = MultipleFilterManager()
    order_manager = DefaultModelOrderManager()

    def _filter_queryset(self, qs):
        """
        :return: filtered queryset via filter manager if filter manager is not None.
        """
        if self.filter_manager:
            return self.filter_manager.filter(self, qs, self.request)
        else:
            return qs

    def _order_queryset(self, qs):
        """
        :return: ordered queryset via order manager if order manager is not None.
        """
        if self.order_manager:
            return self.order_manager.sort(self, qs, self.request)
        else:
            return qs

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

    def _get_name(self):
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
        return rest_modelform_factory(
            self.model, form=form_class, resource_typemapper=self.resource_typemapper,
            auto_related_direct_fields=settings.AUTO_RELATED_DIRECT_FIELDS,
            auto_related_reverse_fields=settings.AUTO_RELATED_REVERSE_FIELDS,
            exclude=exclude, fields=fields,
            formfield_callback=self.formfield_for_dbfield
        )
