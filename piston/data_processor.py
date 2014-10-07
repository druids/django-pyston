import sys
import base64
import cStringIO

from django.forms.fields import FileField

from piston.exception import DataInvalidException
from django.core.files.uploadedfile import InMemoryUploadedFile
from piston.utils import get_resource_of_model
from piston.resource import typemapper
from django.forms.models import ModelMultipleChoiceField
from django.utils.translation import ugettext as _


class DataProcessor(object):
    def __init__(self, request, model, form, inst, via):
        self.model = model
        self.request = request
        self.form = form
        self.inst = inst
        self.via = via

    def _process_value(self, data, files, key, data_item):
        raise NotImplementedError

    def _clear_data(self, data, files):
        return data, files

    def process_data(self, data, files):
        data, files = self.clear_data(data, files)

        self.errors = {}
        for key, data_item in data.items():
            self._process_field(data, files, key, data_item)

        if self.errors:
            raise DataInvalidException(self.errors)
        return data, files


class FileDataPreprocessor(DataProcessor):

    def _process_value(self, data, files, key, data_item):
        field = self.form.fields.get(key)
        if (field and isinstance(field, FileField) and isinstance(data_item, dict) and
            {'filename', 'content', 'content_type'}.issubset(set(data_item.keys()))):
            filename = data_item.get('filename')
            file_content = cStringIO.StringIO(base64.b64decode(data_item.get('content')))
            content_type = data_item.get('content_type')
            charset = data_item.get('charset')
            files[key] = InMemoryUploadedFile(
                file_content, field_name=key, name=filename, content_type=content_type,
                size=sys.getsizeof(file_content), charset=charset
            )


class RelatedObjectsPreprocessor(DataProcessor):

    def _process_multiple_choice_field(self, data, key, data_item, field):
        if isinstance(data_item, dict):
            errors = {}
            add_errors = []
            remove_errors = []

            print self.form.initial.get('key')
'''     data[key] = list(getattr(self.inst, key).all().values_list('pk', flat=True))



            self._add_data_items_to_list(resource, data_items.get('add', []), data[key], add_errors)
            self._remove_data_items_from_list(resource, data_items.get('remove', []), data[key], remove_errors)
            if add_errors:
                errors['add'] = add_errors
            if remove_errors:
                errors['remove'] = remove_errors

        else:
            errors = []
            data[key] = []
            self._add_data_items_to_list(resource, data_items, data[key], errors)'''



    def _process_value(self, data, key, data_item):
        field = self.form.fields.get(key)
        if isinstance(field, ModelMultipleChoiceField):
            self._process_multiple_choice_field(field, data_item)


'''     if field and isinstance(data_item, (list, tuple, dict)) and hasattr(field.get(key), 'queryset'):
            rel_model = field.queryset.model
            resource = self._get_resource(rel_model)
            if resource:
                if isinstance(field, ModelMultipleChoiceField):
                    self._process_list_field(resource, data, key, data_item, rel_model)
                else:
                    self._process_dict_field(resource, data, key, data_item, rel_model)


class DataPostprocessor(DataProcessor):

    def _add_related_items(self, resource, data, list_items, errors, related_obj):
        i = 1
        for rel_obj_data in data:
            if not isinstance(rel_obj_data, dict):
                rel_obj_data = {related_obj.model._meta.pk.name: rel_obj_data}

            rel_obj_data[related_obj.field.name] = self.inst.pk
            try:
                list_items.append(resource._create_or_update(rel_obj_data, self.via).pk)
            except (DataInvalidException, RestException) as ex:
                er = ex.errors
                er.update({'_index': i})
                errors.append(er)
            except TypeError:
                errors.append({'error': _('Field must contains object'), '_index': i})
            i += 1

    # TODO: Throw exception if object does not exists or user has not permissions
    def _remove_related_items(self, resource, data, list_items, errors):
        i = 1
        for data_item in data:
            if isinstance(data_item, dict):
                if data_item.has_key(self.model._meta.pk.name):
                    if data_item.get(self.model._meta.pk.name) in list_items:
                        list_items.remove(data_item.get(self.model._meta.pk.name))
                else:
                    errors.append({'_index': i, 'error': _('Removed element must contain pk')})
            else:
                if data_item in list_items:
                    list_items.remove(data_item)
            i += 1

    def _remove_other_related_objects(self, resource, related_obj, existing_related):
        for reverse_related_obj in resource.model.objects.filter(**{related_obj.field.name: self.inst})\
                                    .exclude(pk__in=existing_related):
            if resource.has_delete_permission(self.request, reverse_related_obj, self.via):
                resource._delete(reverse_related_obj)


    def _process_dict_field(self, resource, data, key, data_item, related_obj):
        related_model_obj = get_object_or_none(related_obj.model, **{related_obj.field.name:self.inst.pk})

        if data_item is None and related_model_obj:
            if resource.has_delete_permission(self.request, related_model_obj, self.via):
                resource._delete(related_model_obj)
            else:
                self.errors[key] = {'error': _('You don not have permisson to delete object')}
        else:
            try:
                data_item[related_obj.field.name] = self.inst.pk

                # Update OneToOne field without pk
                if related_model_obj:
                    data_item[related_obj.model._meta.pk.name] = related_model_obj.pk

                data[key] = resource._create_or_update(data_item, self.via).pk
            except (DataInvalidException, ResourceNotFoundException) as ex:
                self.errors[key] = ex.errors
            except TypeError:
                self.errors[key] = {'error': _('Field must contains object')}

    def _process_list_field(self, resource, data, key, data_items, related_obj):
        """
        Create or update reverse ForeignKey field
        """

        if isinstance(data_items, dict):
            existing_related = list(resource.model.objects.filter(**{related_obj.field.name: self.inst}).values_list('pk', flat=True))
            errors = {}
            add_errors = []
            remove_errors = []

            self._add_related_items(resource, data_items.get('add', []), existing_related, add_errors, related_obj)
            self._remove_related_items(resource, data_items.get('remove', []), existing_related, remove_errors)
            if add_errors:
                errors['add'] = add_errors
            if remove_errors:
                errors['remove'] = remove_errors
        else:
            errors = []
            existing_related = []
            self._add_related_items(resource, data_items, existing_related, errors, related_obj)

        self._remove_other_related_objects(resource, related_obj, existing_related)

        if errors:
            self.errors[key] = errors

    def _process_field(self, data, key, data_item):
        if key not in self.form_fields.keys() and hasattr(self.model, key):
            if isinstance(getattr(self.model, key), ForeignRelatedObjectsDescriptor):
                related_obj = getattr(self.model, key).related
                resource_class = get_resource_of_model(related_obj.model)
                if resource_class:
                    self._process_list_field(resource_class(self.request), data, key, data_item, related_obj)
            elif isinstance(getattr(self.model, key), SingleRelatedObjectDescriptor):
                related_obj = getattr(self.model, key).related
                resource_class = get_resource_of_model(related_obj.model)
                if resource_class:
                    self._process_dict_field(resource_class(), data, key, data_item, related_obj)'''
