import warnings
import django

from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.conf import settings
from django.http import Http404, HttpResponse
from django.db.models.query import QuerySet
from django.utils.decorators import classonlymethod

from .utils import rc, HeadersResult, list_to_dict, dict_to_list
from .serializer import DefaultSerializer


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
                for m in typemapper:
                    return typemapper[m]

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
    def has_read_permission(cls, request, obj=None):
        return 'GET' in cls.allowed_methods

    @classmethod
    def has_create_permission(cls, request, obj=None):
        return 'POST' in cls.allowed_methods

    @classmethod
    def has_update_permission(cls, request, obj=None):
        return 'PUT' in cls.allowed_methods

    @classmethod
    def has_delete_permission(cls, request, obj=None):
        return 'DELETE' in cls.allowed_methods

    @classmethod
    def get_permission_validators(cls):
        all_permissions_validators = {
                                        'GET': cls.has_read_permission,
                                        'PUT': cls.has_update_permission,
                                        'POST': cls.has_create_permission,
                                        'DELETE': cls.has_delete_permission,
                                    }

        permissions_validators = {}
        for allowed_method in cls.allowed_methods:
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
    serializer = DefaultSerializer
    register = False

    @classmethod
    def get_allowed_methods(cls, user, obj):
        allowed_methods = []
        for method, validator in cls.get_permission_validators().items():
            if validator(user, obj):
                allowed_methods.append(method)
        return allowed_methods

    def exists(self, **kwargs):
        raise NotImplementedError

    def read(self, request, *args, **kwargs):
        raise NotImplementedError

    def create(self, request, *args, **kwargs):
        raise NotImplementedError

    def update(self, request, *args, **kwargs):
        raise NotImplementedError

    def delete(self, request, *args, **kwargs):
        raise NotImplementedError

    def get_fields(self, request, result):
        return []

    def serialize(self, request, result):
        return self.serializer(self).serialize(request, result, self.get_fields(request, result))

    def deserialize(self, request):
        return self.serializer(self).deserialize(request)

    def get_result(self, request, *args, **kwargs):
        status_code = 200
        http_headers = {}
        rm = request.method.upper()
        meth = getattr(self, self.callmap.get(rm, ''), None)
        if not meth:
            raise Http404

        result = meth(request, *args, **kwargs)

        if isinstance(result, HeadersResult):
            http_headers = result.http_headers
            status_code = result.status_code
            result = result.result
        return result, http_headers, status_code

    def dispatch(self, request, *args, **kwargs):
        request = self.deserialize(request)

        result, http_headers, status_code = self.get_result(request, *args, **kwargs)
        if self._use_emitter(result):
            status_code = result.status_code
            """ 
             Note: We can't use result.content here because that method attempts to convert the content into a string
             which we don't want. when _is_string/_base_content_is_iter is False _container is the raw data
            """
            result = result._container

        stream, ct = self.serialize(request, result)

        if not isinstance(stream, HttpResponse):
            resp = HttpResponse(stream, content_type=ct, status=status_code)
        else:
            resp = stream

        # resp.streaming = self.stream

        for header, value in self.get_headers(request, http_headers).items():
            resp[header] = value
        return resp

    def _use_emitter(self, result):
        """True iff result is a HttpResponse and contains non-string content."""
        if not isinstance(result, HttpResponse):
            return False
        elif django.VERSION >= (1, 4):
            return result._base_content_is_iter
        else:
            return not result._is_string

    def get_headers(self, request, http_headers):
        from piston.emitters import Emitter

        http_headers['X-Serialization-Format-Options'] = ','.join(Emitter.SerializationTypes)
        http_headers['Cache-Control'] = 'must-revalidate, private'
        return http_headers

    @classonlymethod
    def as_view(cls, **initkwargs):
        def view(request, *args, **kwargs):
            self = cls(**initkwargs)
            self.request = request
            self.args = args
            self.kwargs = kwargs
            return self.dispatch(request, *args, **kwargs)

        return view


class DefaultRestModelResource(object):

    default_fields = ('id', '_obj_name')

    @classmethod
    def _obj_name(cls, obj, request):
        return unicode(obj)


class BaseModelResource(DefaultRestModelResource, BaseResource):

    register = True
    fields = ()
    default_obj_fields = ()
    default_list_fields = ()

    def flatten_dict(self, dct):
        return dict([ (str(k), dct.get(k)) for k in dct.keys() ])

    def queryset(self, request):
        return self.model.objects.all()

    def exists(self, **kwargs):
        try:
            self.model.objects.get(**kwargs)
            return True
        except self.model.DoesNotExist:
            return False

    def read(self, request, *args, **kwargs):
        pkfield = self.model._meta.pk.name

        if pkfield in kwargs:
            try:
                return self.queryset(request).get(pk=kwargs.get(pkfield))
            except ObjectDoesNotExist:
                return rc.NOT_FOUND
            except MultipleObjectsReturned:  # should never happen, since we're using a PK
                return rc.BAD_REQUEST
        else:
            return self.queryset(request).filter(*args, **kwargs)

    def create(self, request, *args, **kwargs):
        attrs = self.flatten_dict(request.data)

        try:
            inst = self.queryset(request).get(**attrs)
            return rc.DUPLICATE_ENTRY
        except self.model.DoesNotExist:
            inst = self.model(**attrs)
            inst.save()
            return inst
        except self.model.MultipleObjectsReturned:
            return rc.DUPLICATE_ENTRY

    def update(self, request, *args, **kwargs):
        pkfield = self.model._meta.pk.name

        if pkfield not in kwargs:
            # No pk was specified
            return rc.BAD_REQUEST

        try:
            inst = self.queryset(request).get(pk=kwargs.get(pkfield))
        except ObjectDoesNotExist:
            return rc.NOT_FOUND
        except MultipleObjectsReturned:  # should never happen, since we're using a PK
            return rc.BAD_REQUEST

        attrs = self.flatten_dict(request.data)
        for k, v in attrs.iteritems():
            setattr(inst, k, v)

        inst.save()
        return rc.ALL_OK

    def delete(self, request, *args, **kwargs):
        try:
            inst = self.queryset(request).get(*args, **kwargs)

            inst.delete()
            return rc.DELETED
        except self.model.MultipleObjectsReturned:
            return rc.DUPLICATE_ENTRY
        except self.model.DoesNotExist:
            return rc.NOT_HERE

    def get_fields(self, request, result):
        allowed_fields = list_to_dict(self.fields)

        fields = {}
        x_fields = request.META.get('HTTP_X_FIELDS', '')
        for field in x_fields.split(','):
            if field in allowed_fields:
                fields[field] = allowed_fields.get(field)

        if fields:
            return dict_to_list(fields)

        if isinstance(result, QuerySet):
            fields = self.default_list_fields
        else:
            fields = self.default_obj_fields

        fields = list_to_dict(fields)

        x_extra_fields = request.META.get('HTTP_X_EXTRA_FIELDS', '')
        for field in x_extra_fields.split(','):
            if field in allowed_fields:
                fields[field] = allowed_fields.get(field)

        return dict_to_list(fields)
