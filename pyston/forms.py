from __future__ import unicode_literals

from dateutil import parser
import six

from django import forms
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.utils.translation import ugettext
from django.utils.encoding import force_text, force_str
from django.http.response import Http404

from chamber.shortcuts import get_object_or_none
from chamber.utils.decorators import classproperty

from .conf import settings as pyston_settings
from .exception import DataInvalidException, RESTException
from .utils.compatibility import get_reverse_field_name, get_model_from_relation, is_reverse_many_to_many
from .utils.helpers import str_to_class


class RESTMetaOptions(object):

    def __init__(self, **kwargs):
        rest_meta_kwargs = {
            'auto_reverse': pyston_settings.AUTO_REVERSE,
        }
        rest_meta_kwargs.update(kwargs)
        for k, v in rest_meta_kwargs.items():
            setattr(self, k, v)


def get_rest_meta_dict(form_cls):
    rest_meta_dict = {}
    for base in form_cls.__bases__[:-1]:
        if isinstance(base, RESTFormMixin):
            rest_meta_dict.update(base._get_rest_meta_dict())
    if hasattr(form_cls, 'RESTMeta'):
        rest_meta_dict.update({k: v for k, v in form_cls.RESTMeta.__dict__.items() if not k.startswith('_')})
    return rest_meta_dict


class RESTFormMixin(object):

    def __init__(self, *args, **kwargs):
        self.origin_initial = kwargs.get('initial', {})
        self.partial_update = kwargs.pop('partial_update', False)
        super(RESTFormMixin, self).__init__(*args, **kwargs)

    def is_invalid(self):
        """
        Validate input data. It uses django forms
        """
        errors = {}
        if not self.is_valid():
            errors = dict([(k, v[0]) for k, v in self.errors.items()])

        if '__all__' in errors:
            del errors['__all__']

        non_field_errors = self.non_field_errors()
        if non_field_errors:
            errors['non-field-errors'] = non_field_errors

        if errors:
            return errors

        return False

    @classproperty
    @classmethod
    def _rest_meta(cls):
        return RESTMetaOptions(**get_rest_meta_dict(cls))

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


class AllFieldsUniqueValidationModelForm(forms.ModelForm):

    def validate_unique(self):
        try:
            self.instance.validate_unique()
        except ValidationError as e:
            self._update_errors(e)


class RESTModelForm(RESTFormMixin, AllFieldsUniqueValidationModelForm):
    pass


class RelatedField(object):

    def __init__(self, resource_class=None):
        self.resource_class = resource_class

    def _get_resource(self, model, request):
        from .serializer import get_resource_class_or_none

        resource_class = self.resource_class

        if isinstance(resource_class, six.string_types):
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
                raise DataInvalidException(ugettext('Data must contain primary key: {}').format(pk_field_name))
        else:
            return data

    def _delete_related_object(self, resource, data, via):
        try:
             resource.delete_obj_with_pk(self._flat_object_to_pk(resource.pk_field_name, data), via)
        except (DataInvalidException, RESTException) as ex:
            raise DataInvalidException(ex.errors if isinstance(ex.errors, dict) else {'error': ex.errors})
        except Http404:
            raise DataInvalidException({'error': ugettext('Object does not exist')})

    def _create_or_update_related_object(self, resource, data, via, partial_update):
        if not isinstance(data, dict):
            raise DataInvalidException({'error': ugettext('Data must be object')})

        try:
            return resource.create_or_update(resource.update_deserialized_data(data), via, partial_update)
        except (DataInvalidException, RESTException) as ex:
            raise DataInvalidException(ex.errors)

    def create_update_or_remove(self, parent_inst, data, via, request, partial_update, form):
        raise NotImplementedError

    def _add_parent_inst_to_obj_data(self, parent_inst, field_name, data):
        data = data.copy()
        data[field_name] = parent_inst.pk
        return data

    def _create_and_return_new_object_pk_list(self, resource, parent_inst, via, data, partial_update,
                                              created_via_field_name=None):
        errors = []
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
            except DataInvalidException as ex:
                rel_obj_errors = ex.errors
                rel_obj_errors['_index'] = i
                errors.append(rel_obj_errors)

        if errors:
            raise DataInvalidException(errors)
        return result


class DirectRelatedField(RelatedField):

    def __init__(self, form, field_name, resource_class=None):
        super(DirectRelatedField, self).__init__(resource_class)
        self.form = form
        self.form_field = self.form.fields[field_name]
        self.field_name = field_name


class SingleRelatedField(DirectRelatedField):

    def create_update_or_remove(self, parent_inst, data, via, request, partial_update, form):
        if isinstance(data, dict):
            resource = self._get_resource(self.form_field.queryset.model, request)
            return self._create_or_update_related_object(resource, data, via, partial_update).pk
        else:
            return data


class MultipleRelatedField(DirectRelatedField):

    def _update_related_objects(self, resource, parent_inst, via, data, partial_update):
        if isinstance(data, (tuple, list)):
            return self._create_and_return_new_object_pk_list(resource, parent_inst, via, data, partial_update)
        else:
            raise DataInvalidException(ugettext('Data must be a collection'))

    def create_update_or_remove(self, parent_inst, data, via, request, partial_update, form):
        resource = self._get_resource(self.form_field.queryset.model, request)
        return self._update_related_objects(resource, parent_inst, via, data, partial_update)


class MultipleStructuredRelatedField(MultipleRelatedField):

    def _remove_related_objects(self, resource, parent_inst, via, data, values):
        errors = []
        result = [force_text(val) for val in values]
        for i, obj in enumerate(data):
            try:
                pk = force_text(self._flat_object_to_pk(resource.pk_field_name, obj))
                if pk in result:
                    result.remove(pk)
                else:
                    errors.append({'error': ugettext('Object does not exist in selected data'), '_index': i})
            except (DataInvalidException, RESTException) as ex:
                rel_obj_errors = ex.errors if isinstance(ex.errors, dict) else {'error': ex.errors}
                rel_obj_errors['_index'] = i
                errors.append(rel_obj_errors)
        if errors:
            raise DataInvalidException(errors)
        return result

    def _add_related_objects(self, resource, parent_inst, via, data, values, partial_update):
        if isinstance(data, (tuple, list)):
            return values + self._create_and_return_new_object_pk_list(resource, parent_inst, via, data, partial_update)
        else:
            raise DataInvalidException(ugettext('Data must be a collection'))

    def _add_and_remove_structured_objects(self, resource, parent_inst, via, data, partial_update):
        errors = {}
        values = self.form_field.prepare_value(
            self.form.initial.get(self.field_name, self.form_field.initial)
        ) or []
        if 'remove' in data:
            try:
                values = self._remove_related_objects(resource, parent_inst, via, data.get('remove'), values)
            except DataInvalidException as ex:
                errors['remove'] = ex.errors
        if 'add' in data:
            try:
                values = self._add_related_objects(resource, parent_inst, via, data.get('add'), values, partial_update)
            except DataInvalidException as ex:
                errors['add'] = ex.errors
        if errors:
            raise DataInvalidException(errors)
        else:
            return values

    def _update_structured_object(self, resource, parent_inst, via, data, partial_update):
        if 'set' in data:
            if {'remove', 'add'} & set(data.keys()):
                raise DataInvalidException(ugettext('set cannot be together with add or remove'))
            try:
                return super(MultipleStructuredRelatedField, self)._update_related_objects(
                    resource, parent_inst, via, data.get('set'), partial_update
                )
            except DataInvalidException as ex:
                raise DataInvalidException({'set': ex.errors})
        else:
            return self._add_and_remove_structured_objects(resource, parent_inst, via, data, partial_update)

    def _update_related_objects(self, resource, parent_inst, via, data, partial_update):
        if isinstance(data, dict):
            return self._update_structured_object(resource, parent_inst, via, data, partial_update)
        else:
            return super(MultipleStructuredRelatedField, self)._update_related_objects(
                resource, parent_inst, via, data, partial_update
            )


class ReverseField(RelatedField):

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
        setattr(parent_inst, getattr(parent_inst.__class__, self.reverse_field_name).cache_name, None)

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
        errors = []
        for i, obj_data in enumerate(data):
            try:
                self._delete_related_object(
                    resource,
                    resource.update_deserialized_data(obj_data) if isinstance(obj_data, dict) else obj_data,
                    via
                )
            except DataInvalidException as ex:
                rel_obj_errors = ex.errors
                rel_obj_errors['_index'] = i
                errors.append(rel_obj_errors)

        if errors:
            raise DataInvalidException(errors)

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
            raise DataInvalidException(ugettext('Data must be a collection'))


class ReverseStructuredManyField(ReverseManyField):

    def _remove_reverse_related_objects(self, resource, parent_inst, via, data, field_name):
        if isinstance(data, (tuple, list)):
            self._delete_reverse_objects(resource, data, via)
        else:
            raise DataInvalidException(ugettext('Data must be a collection'))

    def _add_reverse_related_objects(self, resource, model, parent_inst, via, data, partial_update, field_name):
        if isinstance(data, (tuple, list)):
            new_object_pks = self._create_and_return_new_object_pk_list(resource, parent_inst, via, data,
                                                                        partial_update, field_name)
            return model.objects.filter(pk__in=new_object_pks)
        else:
            raise DataInvalidException(ugettext('Data must be a collection'))

    def _add_and_remove_structured_objects(self, resource, model, parent_inst, field_name, via, data, partial_update):
        errors = {}
        if 'remove' in data:
            try:
                objects_qs = model.objects.none()
                self._remove_reverse_related_objects(resource, parent_inst, via, data.get('remove'), field_name)
            except DataInvalidException as ex:
                errors['remove'] = ex.errors
        if 'add' in data:
            try:
                objects_qs = self._add_reverse_related_objects(
                    resource, model, parent_inst, via, data.get('add'), partial_update, field_name
                )
            except DataInvalidException as ex:
                errors['add'] = ex.errors
        if errors:
            raise DataInvalidException(errors)
        else:
            return objects_qs

    def _update_structured_object(self, resource, model, parent_inst, field_name, via, data, partial_update):
        if 'set' in data:
            if {'remove', 'add'} & set(data.keys()):
                raise DataInvalidException(ugettext('set cannot be together with add or remove'))
            try:
                return super(ReverseStructuredManyField, self)._update_reverse_related_objects(
                    resource, model, parent_inst, field_name, via, data.get('set'), partial_update
                )
            except DataInvalidException as ex:
                raise DataInvalidException({'set': ex.errors})
        else:
            return self._add_and_remove_structured_objects(resource, model, parent_inst, field_name, via, data,
                                                           partial_update)

    def _update_reverse_related_objects(self, resource, model, parent_inst, field_name, via, data, partial_update):
        if isinstance(data, dict):
            return self._update_structured_object(resource, model, parent_inst, field_name, via, data, partial_update)
        else:
            return super(ReverseStructuredManyField, self)._update_reverse_related_objects(
                resource, model, parent_inst, field_name, via, data, partial_update
            )

class ISODateTimeField(forms.DateTimeField):

    def strptime(self, value, format):
        return parser.parse(force_str(value))
