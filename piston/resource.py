import warnings

from django.conf import settings
from django.http import HttpResponse
from django.db.models.query import QuerySet
from django.utils.decorators import classonlymethod
from django.utils.encoding import force_text
from django.db.models.base import Model

from .utils import rc, list_to_dict, dict_to_list, flat_list
from .serializer import ResourceSerializer
from .exception import UnsupportedMediaTypeException, MimerDataException

from functools import update_wrapper
from piston.paginator import Paginator
from piston.response import HeadersResponse, RestErrorResponse, RestErrorsResponse, RestCreatedResponse
from piston.exception import RestException, ConflictException, NotAllowedException, DataInvalidException, \
    ResourceNotFoundException
from django.shortcuts import get_object_or_404
from django.http.response import Http404
from django.db import transaction
from django.forms.models import modelform_factory
from django.core.exceptions import ObjectDoesNotExist
from piston.forms import RestModelForm


typemapper = { }
resource_tracker = [ ]


class ResourceMetaClass(type):
    """
    Metaclass that keeps a registry of class -> resource
    mappings.
    """
    def __new__(cls, name, bases, attrs):
        new_cls = type.__new__(cls, name, bases, attrs)
        if new_cls.register:
            def already_registered(model):
                return typemapper.get(model)

            if hasattr(new_cls, 'model'):
                if already_registered(new_cls.model):
                    if not getattr(settings, 'PISTON_IGNORE_DUPE_MODELS', False):
                        warnings.warn("Resource already registered for model %s, "
                            "you may experience inconsistent results." % new_cls.model.__name__)

                typemapper[new_cls.model] = new_cls

            if name != 'BaseResource':
                resource_tracker.append(new_cls)

        return new_cls


class PermissionsResource(object):

    allowed_methods = ('GET', 'POST', 'PUT', 'DELETE')

    @classmethod
    def has_read_permission(cls, request, obj=None, via=None):
        return 'GET' in cls.allowed_methods

    @classmethod
    def has_create_permission(cls, request, obj=None, via=None):
        return 'POST' in cls.allowed_methods

    @classmethod
    def has_update_permission(cls, request, obj=None, via=None):
        return 'PUT' in cls.allowed_methods

    @classmethod
    def has_delete_permission(cls, request, obj=None, via=None):
        return 'DELETE' in cls.allowed_methods

    @classmethod
    def get_permission_validators(cls, restricted_methods=None):
        all_permissions_validators = {
                                        'GET': cls.has_read_permission,
                                        'PUT': cls.has_update_permission,
                                        'POST': cls.has_create_permission,
                                        'DELETE': cls.has_delete_permission,
                                    }

        permissions_validators = {}

        if restricted_methods:
            allowed_methods = set(restricted_methods) & set(cls.allowed_methods)
        else:
            allowed_methods = set(cls.allowed_methods)

        for allowed_method in allowed_methods:
            permissions_validators[allowed_method] = all_permissions_validators[allowed_method]
        return permissions_validators


class BaseResource(PermissionsResource):
    """
    BaseResource that gives you CRUD for free.
    You are supposed to subclass this for specific
    functionality.

    All CRUD methods (`read`/`update`/`create`/`delete`)
    receive a request as the first argument from the
    resource. Use this for checking `request.user`, etc.
    """
    __metaclass__ = ResourceMetaClass

    allowed_methods = ('GET', 'POST', 'PUT', 'DELETE')
    callmap = { 'GET': 'read', 'POST': 'create',
                'PUT': 'update', 'DELETE': 'delete' }
    serializer = ResourceSerializer
    register = False
    csrf_exempt = True
    cache = None

    def __init__(self, request):
        self.request = request

    @classmethod
    def get_allowed_methods(cls, request, obj, restricted_methods=None):
        allowed_methods = []
        for method, validator in cls.get_permission_validators(restricted_methods).items():
            if validator(request, obj):
                allowed_methods.append(method)
        return allowed_methods

    def _get_serialization_format(self):
        serialization_format = self.request.META.get('HTTP_X_SERIALIZATION_FORMAT',
                                                     self.serializer.SERIALIZATION_TYPES.RAW)
        if serialization_format not in self.serializer.SERIALIZATION_TYPES:
            return self.serializer.SERIALIZATION_TYPES.RAW
        return serialization_format

    def read(self):
        raise NotImplementedError

    def create(self):
        raise NotImplementedError

    def update(self):
        raise NotImplementedError

    def delete(self):
        raise NotImplementedError

    def _is_single_obj_request(self, result):
        return isinstance(result, dict)

    def _get_filtered_fields(self, result):
        allowed_fields = list_to_dict(self.get_fields(obj=result))
        if not allowed_fields:
            return []

        fields = {}
        x_fields = self.request.META.get('HTTP_X_FIELDS', '')
        for field in x_fields.split(','):
            if field in allowed_fields:
                fields[field] = allowed_fields.get(field)

        if fields:
            return dict_to_list(fields)

        if self._is_single_obj_request(result):
            fields = self.get_default_detailed_fields(result)
        else:
            fields = self.get_default_general_fields(result)

        fields = list_to_dict(fields)

        x_extra_fields = self.request.META.get('HTTP_X_EXTRA_FIELDS', '')
        for field in x_extra_fields.split(','):
            if field in allowed_fields:
                fields[field] = allowed_fields.get(field)

        return dict_to_list(fields)

    def _serialize(self, result):
        return self.serializer(self).serialize(
            self.request, result, self._get_filtered_fields(result),
            self._get_serialization_format()
        )

    def _deserialize(self):
        return self.serializer(self).deserialize(self.request)

    def _get_response_data(self):
        status_code = 200
        http_headers = {}
        try:
            self.request = self._deserialize()

            rm = self.request.method.upper()
            meth = getattr(self, self.callmap.get(rm, ''), None)
            if not meth:
                result = rc.NOT_FOUND
            else:
                result = meth()
        except MimerDataException:
            result = rc.BAD_REQUEST
        except UnsupportedMediaTypeException:
            result = rc.UNSUPPORTED_MEDIA_TYPE
        except Http404:
            result = rc.NOT_FOUND
        if isinstance(result, HeadersResponse):
            http_headers = result.http_headers
            status_code = result.status_code
            result = result.result

        if isinstance(result, HttpResponse):
            status_code = result.status_code
            result = result._container
        return result, http_headers, status_code

    def _set_response_headers(self, response, result, http_headers):
        for header, value in self._get_headers(result, http_headers).items():
            response[header] = value

    def _get_response(self):
        result, http_headers, status_code = self._get_response_data()
        try:
            content, ct = self._serialize(result)
        except UnsupportedMediaTypeException:
            content = ''
            status_code = 415

        response = content
        if not isinstance(content, HttpResponse):
            response = HttpResponse(content, content_type=ct, status=status_code)

        self._set_response_headers(response, result, http_headers)
        return response

    def _get_from_cache(self):
        if self.cache:
            return self.cache.get_response(self.request)

    def _store_to_cache(self, response):
        if self.cache:
            self.cache.cache_response(self.request, response)

    def dispatch(self, request, *args, **kwargs):
        response = self._get_from_cache()
        if response:
            return response
        response = self._get_response()
        self._store_to_cache(response)
        return response

    def _get_headers(self, result, http_headers):
        http_headers['X-Serialization-Format-Options'] = ','.join(self.serializer.SERIALIZATION_TYPES)
        http_headers['Cache-Control'] = 'must-revalidate, private'
        http_headers['Allowed'] = ','.join(self.allowed_methods)
        fields = self.get_fields(obj=result)
        if fields:
            http_headers['X-Fields-Options'] = ','.join(flat_list(fields))
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


class DefaultRestObjectResource(object):

    fields = ('id', '_obj_name')
    default_detailed_fields = ('id', '_obj_name')
    default_general_fields = ('id', '_obj_name')
    guest_fields = ('id', '_obj_name')

    def _obj_name(self, obj):
        return force_text(obj)

    def get_fields(self, obj=None):
        return self.fields

    def get_default_detailed_fields(self, obj=None):
        return self.default_detailed_fields

    def get_default_general_fields(self, obj=None):
        return self.default_general_fields

    def get_guest_fields(self, request):
        return self.guest_fields


class BaseObjectResource(DefaultRestObjectResource, BaseResource):

    pk_name = 'pk'

    def _flatten_dict(self, dct):
        return dict([ (str(k), dct.get(k)) for k in dct.keys() ])

    def _get_queryset(self):
        """
        Should return list or db queryset
        """
        raise NotImplementedError

    def _get_object_or_404(self):
        """
        Should return one object
        """
        raise NotImplementedError

    def _filter_queryset(self, qs):
        """
        Should contain implementation for objects filtering
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

    def create(self):
        pk = self.kwargs.get(self.pk_name)
        data = self._flatten_dict(self.request.data)
        if pk and self._exists_obj(pk=pk):
            return rc.DUPLICATE_ENTRY
        try:
            inst = self._atomic_create_or_update(data)
        except DataInvalidException as ex:
            return RestErrorsResponse(ex.errors)
        except RestException as ex:
            return RestErrorResponse(ex.message)
        return RestCreatedResponse(inst)

    def read(self):
        pk = self.kwargs.get(self.pk_name)

        if pk:
            return self._get_object_or_404()

        try:
            qs = self._filter_queryset(self._get_queryset())
            qs = self._order_queryset(qs)
            paginator = Paginator(qs, self.request)
            return HeadersResponse(paginator.page_qs, {'X-Total': paginator.total})
        except RestException as ex:
            return RestErrorResponse(ex.message)
        except Exception as ex:
            return HeadersResponse([], {'X-Total': 0})

    def update(self):
        pk = self.kwargs.get(self.pk_name)
        data = self._flatten_dict(self.request.data)
        data[self.pk_name] = pk
        try:
            return self._atomic_create_or_update(data)
        except DataInvalidException as ex:
            return RestErrorsResponse(ex.errors)
        except ResourceNotFoundException:
            return rc.NOT_FOUND
        except ConflictException as ex:
            return rc.FORBIDDEN
        except RestException as ex:
            return RestErrorResponse(ex.message)

    def delete(self):
        obj = self._get_object_or_404()
        self._pre_delete_obj(obj)
        self._delete_obj(obj)
        self._post_delete_obj(obj)
        return rc.DELETED

    def _pre_delete_obj(self, obj):
        pass

    def _delete_obj(self, obj):
        raise NotImplementedError

    def _post_delete_obj(self, obj):
        pass

    @transaction.atomic
    def _atomic_create_or_update(self, data):
        """
        Atomic object creation
        """
        inst = self._create_or_update(data)
        return inst

    def _get_instance(self, data):
        """
        Should contains implementation for get object according to input data values
        """
        raise NotImplementedError

    def _generate_form_class(self, inst, exclude=[]):
        return self.form_class

    def _get_form(self, fields=None, inst=None, data=None, files=None, initial={}):
        # When is send PUT (resource instance exists), it is possible send only changed values.
        exclude = []

        kwargs = {}
        if inst:
            kwargs['instance'] = inst
        if data is not None:
            kwargs['data'] = data
            kwargs['files'] = files

        form_class = self._generate_form_class(inst, exclude)
        return form_class(initial=initial, **kwargs)

    def _get_form_initial(self, obj):
        return {}

    def _can_save_obj(self, change, inst, form, via):
        if change and not self.has_update_permission(self.request, inst, via=via) and form.has_changed():
            raise NotAllowedException
        elif not change and not self.has_create_permission(self.request, via=via):
            raise NotAllowedException

        return not change or self.has_update_permission(self.request, inst, via=via)

    def _create_or_update(self, data, via=None):
        """
        Helper for creating or updating resource
        """
        if via is None:
            via = []

        inst = self._get_instance(data)
        change = inst and True or False

        files = self.request.FILES
        form_fields = self._get_form(inst=inst, data=data, initial=self._get_form_initial(inst)).fields
        form = self._get_form(fields=form_fields.keys(), inst=inst, data=data, files=files,
                             initial=self._get_form_initial(inst))

        errors = form.is_invalid()
        if errors:
            raise DataInvalidException(errors)

        inst = form.save(commit=False)

        if self._can_save_obj(change, inst, form, via):
            self._pre_save_obj(inst, form, change)
            self._save_obj(inst, form, change)
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


class BaseModelResource(BaseObjectResource):

    register = True
    form_class = RestModelForm

    def _get_queryset(self):
        return self.model.objects.all()

    def _get_object_or_404(self):
        return get_object_or_404(self._get_queryset(), pk=self.kwargs.get(self.pk_name))

    def _exists_obj(self, **kwargs):
        return self.model.objects.filter(**kwargs).exists()

    def _is_single_obj_request(self, result):
        return isinstance(result, Model)

    def _delete_obj(self, obj):
        obj.delete()

    def _save_obj(self, obj, form, change):
        obj.save()

    def _get_exclude(self, obj=None):
        return []

    def _get_form_class(self, inst):
        return self.form_class

    def _get_instance(self, data):
        # If data contains id this method is update otherwise create
        inst = None
        pk = data.get(self.pk_name)
        if pk:
            try:
                inst = self._get_queryset().get(pk=pk)
            except ObjectDoesNotExist:
                if self.model.objects.filter(pk=pk).exists():
                    raise ConflictException
        return inst

    def _get_form_fields(self, obj=None):
        return None

    def _generate_form_class(self, inst, exclude=[]):
        exclude = list(self._get_exclude(inst)) + exclude
        form_class = self._get_form_class(inst)
        fields = self._get_form_fields(inst)

        if hasattr(form_class, '_meta') and form_class._meta.exclude:
            exclude.extend(form_class._meta.exclude)
        return modelform_factory(self.model, form=form_class, exclude=exclude, fields=fields)
