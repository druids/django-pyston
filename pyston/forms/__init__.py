from dateutil import parser
import copy

from collections import OrderedDict

from django import forms
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError, ImproperlyConfigured
from django.http.response import Http404
from django.forms.models import ModelFormMetaclass, modelform_factory
from django.utils.translation import ugettext
from django.utils.encoding import force_text, force_str

from chamber.shortcuts import get_object_or_none
from chamber.utils.decorators import classproperty

from pyston.conf import settings as pyston_settings
from pyston.exception import DataInvalidException, RESTException
from pyston.utils.compatibility import (
    get_reverse_field_name, get_model_from_relation, is_reverse_many_to_many, is_reverse_one_to_one,
    is_reverse_many_to_one, delete_cached_value
)
from pyston.utils.helpers import str_to_class


DEFAULT_CODE = 'invalid'


class RESTError(Exception):
    pass


class RESTListError(RESTError):
    """
    List exception is standard list object that can be raised like exception.
    """

    def __init__(self, data=None):
        super(RESTListError, self).__init__()
        self._list = list(data) if data is not None else []

    def __repr__(self):
        return "<{0} {1}>".format(self.__class__.__name__, self._list)

    def __len__(self):
        return len(self._list)

    def __getitem__(self, i):
        return self._list[i]

    def __delitem__(self, i):
        del self._list[i]

    def __setitem__(self, i, val):
        self._list[i] = val

    def __str__(self):
        return str(self._list)

    def insert(self, i, val):
        self._list.insert(i, val)

    def append(self, val):
        self._list.append(val)


class RESTDictError(RESTError):
    """
    Dict exception is standard dict object that can be raised like exception.
    """

    def __init__(self, data=None):
        super(RESTDictError, self).__init__()
        self._dict = dict(data) if data is not None else {}

    def __setitem__(self, key, item):
        self._dict[key] = item

    def __getitem__(self, key):
        return self._dict[key]

    def __contains__(self, key):
        return key in self._dict

    def __repr__(self):
        return '<{0} {1}>'.format(self.__class__.__name__, self._dict)

    def __str__(self):
        return str(self._dict)

    def __len__(self):
        return len(self._dict)

    def __delitem__(self, key):
        del self._dict[key]

    def clear(self):
        return self._dict.clear()

    def has_key(self, k):
        return k in self._dict

    def update(self, *args, **kwargs):
        return self._dict.update(*args, **kwargs)

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    def items(self):
        return self._dict.items()

    def pop(self, key):
        return self._dict.pop(key)


class RESTDictIndexError(RESTError):

    def __init__(self, index, data):
        super(RESTDictIndexError, self).__init__()
        self.index = index
        self.data = RESTDictError(data)

    def __repr__(self):
        return "<{0} {1}: {2}>".format(self.__class__.__name__, self.index, self.data)

    def __str__(self):
        return str(self.data)


class RESTValidationError(RESTError):

    def __init__(self, message, code=None):
        if isinstance(message, RESTValidationError):
            self.message = message.message
            self.code = message.code
        else:
            self.message = message
            self.code = code or DEFAULT_CODE

    def __str__(self):
        return self.message


class AllFieldsUniqueValidationModelForm(forms.ModelForm):

    def validate_unique(self):
        try:
            self.instance.validate_unique()
        except ValidationError as e:
            self._update_errors(e)


class RelatedField:

    is_reverse = False

    def __init__(self, resource_class=None):
        self.resource_class = resource_class

    def _get_resource(self, model, request):
        from pyston.serializer import get_resource_class_or_none

        resource_class = self.resource_class

        if isinstance(resource_class, str):
            resource_class = str_to_class(resource_class)
        elif resource_class is None:
            resource_class = get_resource_class_or_none(model)
        assert resource_class, 'Missing resource for model {}'.format(model)
        return resource_class(request)

    def _flat_object_to_pk(self, pk_field_name, data):
        if isinstance(data, dict):
            try:
                return data[pk_field_name]
            except KeyError:
                raise RESTValidationError(
                    ugettext('Data must contain primary key: {}').format(pk_field_name), code='invalid_structure'
                )
        else:
            return data

    def _delete_related_object(self, resource, data, via):
        try:
             resource.delete_obj_with_pk(self._flat_object_to_pk(resource.pk_field_name, data), via)
        except DataInvalidException as ex:
            raise ex.errors
        except RESTException as ex:
            raise RESTValidationError(ex.message)
        except Http404:
            raise RESTValidationError(ugettext('Object does not exist'), code='invalid_structure')

    def _create_or_update_related_object(self, resource, data, via, partial_update):
        if not isinstance(data, dict):
            raise RESTValidationError(ugettext('Data must be object'), code='invalid_structure')

        try:
            return resource.create_or_update(resource.update_deserialized_data(data), via, partial_update)
        except DataInvalidException as ex:
            raise ex.errors
        except RESTException as ex:
            raise RESTValidationError(ex.errors)

    def create_update_or_remove(self, parent_inst, data, via, request, partial_update, form):
        raise NotImplementedError

    def _add_parent_inst_to_obj_data(self, parent_inst, field_name, data):
        data = data.copy()
        data[field_name] = parent_inst.pk
        return data

    def _create_and_return_new_object_pk_list(self, resource, parent_inst, via, data, partial_update,
                                              created_via_field_name=None):
        errors = RESTListError()
        result = []
        for i, obj_data in enumerate(data):
            if not isinstance(obj_data, dict):
                obj_data = {resource.pk_field_name: force_text(obj_data)}

            try:
                if created_via_field_name:
                    obj_data = self._add_parent_inst_to_obj_data(parent_inst, created_via_field_name, obj_data)

                if set(obj_data.keys()) ^ {resource.pk_field_name}:
                    result.append(self._create_or_update_related_object(resource, obj_data, via, partial_update).pk)
                else:
                    result.append(obj_data[resource.pk_field_name])
            except RESTDictError as ex:
                errors.append(RESTDictIndexError(i, ex))
            except RESTError as ex:
                errors.append(RESTDictIndexError(i, {'error': ex}))

        if errors:
            raise errors
        return result


class DirectRelatedField(RelatedField):

    def __init__(self, field_name, form_field=None, resource_class=None):
        super(DirectRelatedField, self).__init__(resource_class)
        self.form_field = form_field
        self.field_name = field_name


class SingleRelatedField(DirectRelatedField):

    def create_update_or_remove(self, parent_inst, data, via, request, partial_update, form):
        if isinstance(data, dict):
            resource = self._get_resource(self.form_field.queryset.model, request)
            return self._create_or_update_related_object(resource, data, via, partial_update).pk
        else:
            return data


class MultipleRelatedField(DirectRelatedField):

    def _update_related_objects(self, resource, parent_inst, via, data, partial_update, form):
        if isinstance(data, (tuple, list)):
            return self._create_and_return_new_object_pk_list(resource, parent_inst, via, data, partial_update)
        else:
            raise RESTValidationError(ugettext('Data must be a collection'), code='invalid_structure')

    def create_update_or_remove(self, parent_inst, data, via, request, partial_update, form):
        resource = self._get_resource(self.form_field.queryset.model, request)
        return self._update_related_objects(resource, parent_inst, via, data, partial_update, form)


class MultipleStructuredRelatedField(MultipleRelatedField):

    def _remove_related_objects(self, resource, parent_inst, via, data, values):
        errors = RESTListError()
        result = [force_text(val) for val in values]
        for i, obj in enumerate(data):
            try:
                pk = force_text(self._flat_object_to_pk(resource.pk_field_name, obj))
                if pk in result:
                    result.remove(pk)
                else:
                    errors.append({'error': ugettext('Object does not exist in selected data'), '_index': i})
            except RESTDictError as ex:
                errors.append(RESTDictIndexError(i, ex))
            except RESTError as ex:
                errors.append(RESTDictIndexError(i, {'error': ex}))

        if errors:
            raise errors
        return result

    def _add_related_objects(self, resource, parent_inst, via, data, values, partial_update):
        if isinstance(data, (tuple, list)):
            return values + self._create_and_return_new_object_pk_list(resource, parent_inst, via, data, partial_update)
        else:
            raise RESTValidationError(ugettext('Data must be a collection'), code='invalid_structure')

    def _add_and_remove_structured_objects(self, resource, parent_inst, via, data, partial_update, form):
        errors = RESTDictError()
        values = self.form_field.prepare_value(form.initial.get(self.field_name, self.form_field.initial)) or []
        if 'remove' in data:
            try:
                values = self._remove_related_objects(resource, parent_inst, via, data.get('remove'), values)
            except RESTError as ex:
                errors['remove'] = ex
        if 'add' in data:
            try:
                values = self._add_related_objects(resource, parent_inst, via, data.get('add'), values, partial_update)
            except RESTError as ex:
                errors['add'] = ex
        if errors:
            raise errors
        else:
            return values

    def _update_structured_object(self, resource, parent_inst, via, data, partial_update, form):
        if 'set' in data:
            if {'remove', 'add'} & set(data.keys()):
                raise RESTValidationError(
                    ugettext('set cannot be together with add or remove'), code='invalid_structure'
                )
            try:
                return super(MultipleStructuredRelatedField, self)._update_related_objects(
                    resource, parent_inst, via, data.get('set'), partial_update, form
                )
            except RESTError as ex:
                raise RESTDictError({'set': ex})
        else:
            return self._add_and_remove_structured_objects(resource, parent_inst, via, data, partial_update, form)

    def _update_related_objects(self, resource, parent_inst, via, data, partial_update, form):
        if isinstance(data, dict):
            return self._update_structured_object(resource, parent_inst, via, data, partial_update, form)
        else:
            return super(MultipleStructuredRelatedField, self)._update_related_objects(
                resource, parent_inst, via, data, partial_update, form
            )


class ReverseField(RelatedField):

    is_reverse = True

    def __init__(self, reverse_field_name, extra_data=None, resource_class=None):
        super(ReverseField, self).__init__(resource_class)
        self.reverse_field_name = reverse_field_name
        self.extra_data = extra_data

    def _get_extra_data(self, parent_inst):
        return self.extra_data


class ReverseSingleField(ReverseField):

    def _get_obj_or_none(self, model, parent_inst, field_name):
        return None

    def _remove(self, resource, parent_inst, related_obj, field_name, via):
        self._delete_related_object(
            resource, {resource.pk_field_name: related_obj.pk}, via
        )

    def _create_or_update(self, resource, parent_inst, related_obj, field_name, via, data, partial_update):
        if not isinstance(data, dict):
            obj_data = {resource.pk_field_name: force_text(data)}
        else:
            obj_data = data.copy()

        extra_data = self._get_extra_data(parent_inst)
        if extra_data:
            obj_data.update(extra_data)

        if resource.pk_field_name not in obj_data and related_obj:
            obj_data[resource.pk_field_name] = related_obj.pk
        obj_data[field_name] = parent_inst.pk
        return self._create_or_update_related_object(resource, obj_data, via, partial_update)

    def create_update_or_remove(self, parent_inst, data, via, request, partial_update, form):
        model = get_model_from_relation(parent_inst.__class__, self.reverse_field_name)
        field_name = get_reverse_field_name(parent_inst.__class__, self.reverse_field_name)
        resource = self._get_resource(model, request)
        related_obj = self._get_obj_or_none(model, parent_inst, field_name)
        if data is None and related_obj:
            self._remove(resource, parent_inst, related_obj, field_name, via)
            return None
        elif data is not None:
            return self._create_or_update(resource, parent_inst, related_obj, field_name, via, data, partial_update)


class ReverseOneToOneField(ReverseSingleField):

    def _get_obj_or_none(self, model, parent_inst, field_name):
        return get_object_or_none(model, **{field_name: parent_inst.pk})

    def _remove(self, resource, parent_inst, related_obj, field_name, via):
        super(ReverseOneToOneField, self)._remove(resource, parent_inst, related_obj, field_name, via)
        delete_cached_value(parent_inst, self.reverse_field_name)

    def _create_or_update(self, resource, parent_inst, related_obj, field_name, via, data, partial_update):
        obj = super(ReverseOneToOneField, self)._create_or_update(resource, parent_inst, related_obj, field_name, via,
                                                                  data, partial_update)
        setattr(parent_inst, self.reverse_field_name, obj)
        return obj


class ReverseManyField(ReverseField):

    is_deleted_not_selected_objects = True

    def _add_parent_inst_to_obj_data(self, parent_inst, field_name, data):
        if is_reverse_many_to_many(parent_inst, self.reverse_field_name):
            data = data.copy()
            data[field_name] = {'add': [parent_inst.pk]}
            return data
        else:
            return super(ReverseManyField, self)._add_parent_inst_to_obj_data(parent_inst, field_name, data)

    def _delete_reverse_objects(self, resource, data, via):
        errors = RESTListError()
        for i, obj_data in enumerate(data):
            try:
                self._delete_related_object(
                    resource,
                    resource.update_deserialized_data(obj_data) if isinstance(obj_data, dict) else obj_data,
                    via
                )
            except RESTDictError as ex:
                errors.append(RESTDictIndexError(i, ex))
            except RESTError as ex:
                errors.append(RESTDictIndexError(i, {'error': ex}))

        if errors:
            raise errors

    def create_update_or_remove(self, parent_inst, data, via, request, partial_update, form):
        model = get_model_from_relation(parent_inst.__class__, self.reverse_field_name)
        field_name = get_reverse_field_name(parent_inst.__class__, self.reverse_field_name)
        resource = self._get_resource(model, request)
        return self._update_reverse_related_objects(resource, model, parent_inst, field_name, via, data, partial_update)

    def _update_reverse_related_objects(self, resource, model, parent_inst, field_name, via, data, partial_update):
        if isinstance(data, (tuple, list)):
            new_object_pks = self._create_and_return_new_object_pk_list(resource, parent_inst, via, data,
                                                                        partial_update, field_name)
            # This is not optimal solution but is the most universal
            if self.is_deleted_not_selected_objects:
                self._delete_reverse_objects(
                    resource, resource._get_queryset().filter(**{field_name: parent_inst}).exclude(
                        pk__in=new_object_pks
                    ).values_list('pk', flat=True),
                    via
                )
            return model.objects.filter(pk__in=new_object_pks)
        else:
            raise RESTValidationError(ugettext('Data must be a collection'), code='invalid_structure')


class ReverseStructuredManyField(ReverseManyField):

    def _remove_reverse_related_objects(self, resource, parent_inst, via, data, field_name):
        if isinstance(data, (tuple, list)):
            self._delete_reverse_objects(resource, data, via)
        else:
            raise RESTValidationError(ugettext('Data must be a collection'), code='invalid_structure')

    def _add_reverse_related_objects(self, resource, model, parent_inst, via, data, partial_update, field_name):
        if isinstance(data, (tuple, list)):
            new_object_pks = self._create_and_return_new_object_pk_list(resource, parent_inst, via, data,
                                                                        partial_update, field_name)
            return model.objects.filter(pk__in=new_object_pks)
        else:
            raise RESTValidationError(ugettext('Data must be a collection'), code='invalid_structure')

    def _add_and_remove_structured_objects(self, resource, model, parent_inst, field_name, via, data, partial_update):
        errors = RESTDictError()
        if 'remove' in data:
            try:
                objects_qs = model.objects.none()
                self._remove_reverse_related_objects(resource, parent_inst, via, data.get('remove'), field_name)
            except RESTError as ex:
                errors['remove'] = ex
        if 'add' in data:
            try:
                objects_qs = self._add_reverse_related_objects(
                    resource, model, parent_inst, via, data.get('add'), partial_update, field_name
                )
            except RESTError as ex:
                errors['add'] = ex
        if errors:
            raise errors
        else:
            return objects_qs

    def _update_structured_object(self, resource, model, parent_inst, field_name, via, data, partial_update):
        if 'set' in data:
            if {'remove', 'add'} & set(data.keys()):
                raise RESTValidationError(
                    ugettext('set cannot be together with add or remove'), code='invalid_structure'
                )
            try:
                return super(ReverseStructuredManyField, self)._update_reverse_related_objects(
                    resource, model, parent_inst, field_name, via, data.get('set'), partial_update
                )
            except RESTError as ex:
                raise RESTDictError({'set': ex})
        else:
            return self._add_and_remove_structured_objects(resource, model, parent_inst, field_name, via, data,
                                                           partial_update)

    def _update_reverse_related_objects(self, resource, model, parent_inst, field_name, via, data, partial_update):
        if isinstance(data, dict) and data and set(data.keys()) <= {'add', 'remove', 'set'}:
            return self._update_structured_object(resource, model, parent_inst, field_name, via, data, partial_update)
        else:
            return super(ReverseStructuredManyField, self)._update_reverse_related_objects(
                resource, model, parent_inst, field_name, via, data, partial_update
            )


class ISODateTimeField(forms.DateTimeField):

    def strptime(self, value, format):
        return parser.parse(force_str(value))


class RESTFormMixin:

    def __init__(self, *args, **kwargs):
        self.origin_initial = kwargs.get('initial', {})
        self.partial_update = kwargs.pop('partial_update', False)
        super(RESTFormMixin, self).__init__(*args, **kwargs)

    def _parse_rest_errors(self, errors):
        if isinstance(errors, RESTError):
            return errors
        elif isinstance(errors, dict):
            return RESTDictError({k: self._parse_rest_errors(v) for k, v in errors.items()})
        else:
            return RESTValidationError(list(errors.as_data()[0])[0], errors.as_data()[0].code)

    def is_invalid(self):
        """
        Validate input data. It uses django forms
        """
        errors = RESTDictError() if self.is_valid() else self._parse_rest_errors(self.errors)

        if '__all__' in errors:
            del errors['__all__']

        non_field_errors = self.non_field_errors()
        if non_field_errors:
            errors['non-field-errors'] = self._parse_rest_errors(non_field_errors)

        if errors:
            return errors

        return False

    def is_valid(self):
        self.origin_data = self.data
        # For partial update is used model values
        # for other cases is used only default values and redefined initial values during form initialization
        self._merge_from_initial(self.initial if self.partial_update else self.origin_initial)
        return super(RESTFormMixin, self).is_valid()

    """
    Subclass of `forms.ModelForm` which makes sure
    that the initial values are present in the form
    data, so you don't have to send all old values
    for the form to actually validate. Django does not
    do this on its own, which is really annoying.
    """
    def _merge_from_initial(self, initial):
        self.data = self.data.copy()
        filt = lambda v: v not in self.data.keys()
        for field_name in filter(filt, self.fields.keys()):
            field = self.fields[field_name]
            self.data[field_name] = field.prepare_value(initial.get(field_name, field.initial))

    def add_error(self, field, error):
        """
        Standard django form does not support more structured errors
        (for example error dict that contains another error dict).
        For this purpose pyston creates RESTError class and we must rewrite this method to allow these
        complex error messages.
        """
        if isinstance(error, RESTError):
            if not field:
                raise ValueError('Field must be set for RESTError')
            self._errors[field] = error
        else:
            if not isinstance(error, ValidationError):
                # Normalize to ValidationError and let its constructor
                # do the hard work of making sense of the input.
                error = ValidationError(error)

            if hasattr(error, 'error_dict'):
                if field is not None:
                    raise TypeError(
                        "The argument `field` must be `None` when the `error` "
                        "argument contains errors for multiple fields."
                    )
                else:
                    error = error.error_dict
            else:
                error = {field or NON_FIELD_ERRORS: error.error_list}

            for field, error_list in error.items():
                if field not in self.errors:
                    if field == NON_FIELD_ERRORS:
                        self._errors[field] = self.error_class(error_class='nonfield')
                    else:
                        self._errors[field] = self.error_class()
                self._errors[field].extend(error_list)
                if field in self.cleaned_data:
                    del self.cleaned_data[field]


def get_resource_class( model, resource_typemapper):
    from pyston.serializer import get_resource_class_or_none

    return get_resource_class_or_none(model, resource_typemapper)


def direct_related_fields_for_model(base_fields, resource_typemapper=None):
    """
    Generate direct from form fields.
    """

    related_fields = OrderedDict()
    for name, field in base_fields.items():
        if isinstance(field, forms.ModelMultipleChoiceField):
            resource_class = get_resource_class(field.queryset.model, resource_typemapper)
            if resource_class:
                related_fields[name] = MultipleStructuredRelatedField(
                    name, form_field=field, resource_class=resource_class
                )
        elif isinstance(field, forms.ModelChoiceField):
            resource_class = get_resource_class(field.queryset.model, resource_typemapper)
            if resource_class:
                related_fields[name] = SingleRelatedField(
                    name, form_field=field, resource_class=resource_class
                )
    return related_fields


def reverse_related_fields_for_model(model, fields=None, exclude=None, resource_typemapper=None):
    """
    Generate reverse related fields for concrete model.
    """

    field_list = []
    opts = model._meta
    reverse_fields = [
        f for f in opts.get_fields()
        if (f.one_to_many or f.one_to_one or f.many_to_many)
        and f.auto_created and not f.concrete
    ]
    for f in reverse_fields:
        if fields is not None and f.name not in fields:
            continue
        if exclude and f.name in exclude:
            continue
        if not f.related_name:
            continue

        resource_class = get_resource_class(get_model_from_relation(model, f.name), resource_typemapper)

        if resource_class and (is_reverse_many_to_many(model, f.name) or is_reverse_many_to_one(model, f.name)):
            field_list.append((f.name, ReverseStructuredManyField(f.name, resource_class=resource_class)))
        elif resource_class and is_reverse_one_to_one(model, f.name):
            field_list.append((f.name, ReverseOneToOneField(f.name, resource_class=resource_class)))

    return OrderedDict(field_list)


class RESTModelFormOptions:

    def __init__(self, options=None):
        self.resource_typemapper = getattr(options, 'resource_typemapper', None)
        self.auto_related_direct_fields = getattr(options, 'auto_related_direct_fields', False)
        self.auto_related_reverse_fields = getattr(options, 'auto_related_reverse_fields', False)


class RESTFormMetaclass(ModelFormMetaclass):
    """
    Form metaclass that improves django model form with reverse fields.
    """

    def __new__(cls, name, bases, attrs):
        # Collect related fields from current class.
        current_related_fields = []
        for key, value in list(attrs.items()):
            if isinstance(value, RelatedField):
                current_related_fields.append((key, value))
                attrs.pop(key)
                if not value.is_reverse and value.form_field:
                    attrs[key] = value.form_field

        attrs['declared_related_fields'] = OrderedDict(current_related_fields)

        new_class = super(RESTFormMetaclass, cls).__new__(cls, name, bases, attrs)

        rest_opts = new_class._rest_meta = RESTModelFormOptions(getattr(new_class, 'RESTMeta', None))

        # Walk through the MRO.
        declared_related_fields = OrderedDict()
        for base in reversed(new_class.__mro__):
            # Collect fields from base class.
            if hasattr(base, 'declared_related_fields'):
                declared_related_fields.update(base.declared_related_fields)

            # Field shadowing.
            for attr, value in base.__dict__.items():
                if value is None and attr in declared_related_fields:
                    declared_related_fields.pop(attr)

        opts = new_class._meta

        new_class.base_related_fields = declared_related_fields
        new_class.declared_related_fields = declared_related_fields

        if opts.model:
            reverse_related_fields = reverse_related_fields_for_model(
                opts.model, opts.fields, opts.exclude, rest_opts.resource_typemapper
            ) if rest_opts.auto_related_reverse_fields else {}

            direct_related_fields = direct_related_fields_for_model(
                new_class.base_fields, rest_opts.resource_typemapper
            ) if rest_opts.auto_related_direct_fields else {}
            related_fields = reverse_related_fields
            related_fields.update(direct_related_fields)
            related_fields.update(declared_related_fields)

            for name, field in related_fields.items():
                if not field.is_reverse and name not in new_class.base_fields:
                    raise ValueError("Missing django form field for related field field '{}'".format(name))
                elif not field.is_reverse:
                    field.form_field = new_class.base_fields[name]

        else:
            related_fields = declared_related_fields

        new_class.base_related_fields = related_fields
        new_class.declared_related_fields = related_fields

        return new_class


class RESTModelForm(RESTFormMixin, AllFieldsUniqueValidationModelForm, metaclass=RESTFormMetaclass):

    def __init__(self, *args, **kwargs):
        super(RESTModelForm, self).__init__(*args, **kwargs)
        self.related_fields = copy.deepcopy(self.base_related_fields)

    def _reverse_fields_clean(self):
        """
        Call clean methods on reverse fields.
        """
        for name, field in self.related_fields.items():
            if field.is_reverse and hasattr(self, 'clean_{}'.format(name)):
                try:
                    getattr(self, 'clean_{}'.format(name))()
                except (ValidationError, RESTError) as e:
                    self.add_error(name, e)

    def _post_save_clean(self):
        """
        Reverse related fields can be validated after current object save.
        """
        self._reverse_fields_clean()

    def _pre_save(self, obj):
        pass

    def _post_save(self, obj):
        pass

    def _set_post_save(self, commit, obj):
        """
        Default django form is updated with pre, post save methods and post save clean.
        For this purpose is used django default method save_m2m. But for cleaner code can be used method post_save.
        """
        if commit:
            self._post_save(obj)
        else:
            self.old_save_m2m = self.save_m2m

            def post_save():
                self.old_save_m2m()
                self._post_save_clean()
                self._post_save(obj)
            self.save_m2m = post_save
            self.post_save = post_save

    def save(self, commit=True):
        """
        Updates default save method with pre and post save methods.
        """
        obj = super(RESTModelForm, self).save(commit=False)
        self._pre_save(obj)
        if commit:
            obj.save()
        self._set_post_save(commit, obj)
        return obj


def rest_modelform_factory(model, form=RESTModelForm, form_factory=modelform_factory, resource_typemapper=None,
                           auto_related_direct_fields=None, auto_related_reverse_fields=None, **kwargs):
    """
    Purpose of the rest factory form method is prepare RESTMeta for standard django model form.
    The final form is created using a factory defined in form_factory argument.
    :param model: Django model class
    :param form: base model form class
    :param form_factory: provides posibility to change default modelform_factory
    :param resource_typemapper: resource typemapper defines which resources will be used for generation reverse fields
    :param auto_related_direct_fields: defines if form will auto generate direct related REST fields
    :param auto_related_reverse_fields: defines if form will auto generate reverse related REST fields
    :param kwargs: kwargs of form_factory
    :return: django model form class
    """
    attrs = {}
    if resource_typemapper:
        attrs['resource_typemapper'] = resource_typemapper
    if auto_related_direct_fields:
        attrs['auto_related_direct_fields'] = auto_related_direct_fields
    if auto_related_reverse_fields:
        attrs['auto_related_reverse_fields'] = auto_related_reverse_fields

    parent = (object,)
    if hasattr(form, 'RESTMeta'):
        parent = (form.RESTMeta, object)

    RESTMeta = type(str('RESTMeta'), parent, attrs)

    # Give this new form class a reasonable name.
    form_class_name = model.__name__ + str('Form')

    # Class attributes for the new form class.
    form_class_attrs = {
        'RESTMeta': RESTMeta,
    }
    # Instantiate type(form) in order to use the same metaclass as form.
    return form_factory(model, form=type(form)(form_class_name, (form,), form_class_attrs), **kwargs)
