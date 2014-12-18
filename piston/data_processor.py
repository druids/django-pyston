import sys
import base64
import cStringIO
import inspect

from django.forms.fields import FileField
from django.utils.translation import ugettext_lazy as _
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models.fields.related import ForeignRelatedObjectsDescriptor, SingleRelatedObjectDescriptor
from django.forms.models import ModelChoiceField, ModelMultipleChoiceField
from django.http.response import Http404
from django.utils.encoding import force_text

from chamber.models.shortcuts import get_object_or_none

from .exception import DataInvalidException, RestException
from .resource import BaseObjectResource, typemapper, BaseModelResource


class DataProcessorCollection(object):

    def __init__(self):
        self.data_processors_map = {}

    def register(self, resource_class):
        def _register(processor_class):
            data_processors = self.data_processors_map.get(resource_class, set())
            data_processors.add(processor_class)
            self.data_processors_map[resource_class] = data_processors
            return processor_class
        return _register

    def get_processors(self, resource_class):
        processors = []
        for obj_class in inspect.getmro(resource_class):
            processors += list(self.data_processors_map.get(obj_class, set()))
        return processors

data_preprocessors = DataProcessorCollection()
data_postprocessors = DataProcessorCollection()


class DataProcessor(object):
    def __init__(self, resource, form, inst, via):
        self.resource = resource
        self.model = resource.model
        self.request = resource.request
        self.form = form
        self.inst = inst
        self.via = resource._get_via(via)

    def _process_field(self, data, files, key, data_item):
        raise NotImplementedError

    def _clear_data(self, data, files):
        return data, files

    def process_data(self, data, files):
        data, files = self._clear_data(data, files)

        self.errors = {}
        for key, data_item in data.items():
            self._process_field(data, files, key, data_item)

        if self.errors:
            raise DataInvalidException(self.errors)
        return data, files


@data_preprocessors.register(BaseObjectResource)
class FileDataPreprocessor(DataProcessor):

    def _process_field(self, data, files, key, data_item):
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
            data[key] = filename


class ResourceProcessorMixin(object):

    def _create_or_update_related_object(self, data, model):
        if not isinstance(data, dict):
            raise DataInvalidException({'error': _('Data must be object')})

        resource = self._get_resource(model)
        if resource:
            try:
                return resource._create_or_update(data, self.via)
            except (DataInvalidException, RestException) as ex:
                raise DataInvalidException(ex.errors)

    def _create_and_return_new_object_pk_list(self, data, model, created_via_inst, created_via_field_name=None):
        resource = self._get_resource(model)
        assert resource is not None

        errors = []
        result = []
        i = 0
        for obj_data in data:
            if not isinstance(obj_data, (dict, list)):
                obj_data = {resource.pk_field_name: obj_data}

            try:
                if created_via_field_name:
                    obj_data[created_via_field_name] = created_via_inst.pk

                related_obj = self._create_or_update_related_object(obj_data, model)
                if related_obj:
                    result.append(related_obj.pk)
            except DataInvalidException as ex:
                rel_obj_errors = ex.errors
                rel_obj_errors['_index'] = i
                errors.append(rel_obj_errors)
            except TypeError:
                errors.append({'error': _('Data must be object'), '_index':i})
            i += 1

        if errors:
            raise DataInvalidException(errors)
        return result

    def _delete_reverse_object(self, obj_data, model):
        resource = self._get_resource(model)
        assert resource is not None

        try:
            resource._delete(self._flat_object_to_pk(resource.pk_field_name, obj_data), self.via)
        except (DataInvalidException, RestException) as ex:
            raise DataInvalidException(ex.errors)
        except Http404:
            raise DataInvalidException({'error': _('Object does not exist')})

    def _delete_reverse_objects(self, data, model):
        resource = self._get_resource(model)
        assert resource is not None

        errors = []
        i = 0
        for obj_data in data:
            try:
                self._delete_reverse_object(obj_data, model)
            except DataInvalidException as ex:
                rel_obj_errors = ex.errors
                rel_obj_errors['_index'] = i
                errors.append(rel_obj_errors)
            i += 1
        if errors:
            raise DataInvalidException(errors)

    def _flat_object_to_pk(self, pk_field_name, data):
        i = 0
        if isinstance(data, dict):
            try:
                return data[pk_field_name]
            except KeyError:
                raise DataInvalidException({'error': _('Data must contain primary key: %s') % pk_field_name,
                                            '_index': i})
        else:
            return data

    def _get_resource(self, model):
        resource_class = typemapper.get(model)
        if resource_class:
            return resource_class(self.request)


class MultipleDataProcessorMixin(object):

    INVALID_COLLECTION_EXCEPTION = {'error': _('Data must be a collection')}

    def _append_errors(self, key, operation, errors):
        self.errors[key] = self.errors.get(key, {})
        self.errors[key].update({operation: errors})


@data_preprocessors.register(BaseObjectResource)
class ModelDataPreprocessor(ResourceProcessorMixin, DataProcessor):

    def _process_field(self, data, files, key, data_item):
        field = self.form.fields.get(key)
        if (field and isinstance(field, ModelChoiceField) and not isinstance(field, ModelMultipleChoiceField)
            and data_item and isinstance(data_item, dict)):
            try:
                related_obj = self._create_or_update_related_object(data_item, self.form.fields.get(key).queryset.model)
                if related_obj:
                    data[key] = related_obj.pk
            except DataInvalidException as ex:
                self.errors[key] = ex.errors


@data_preprocessors.register(BaseObjectResource)
class ModelMultipleDataPreprocessor(MultipleDataProcessorMixin, ResourceProcessorMixin, DataProcessor):

    def _create_or_update_related_objects_set(self, data, key, data_item, model):
        if isinstance(data, (tuple, list)):
            try:
                return self._create_and_return_new_object_pk_list(data, model, self.inst)
            except DataInvalidException as ex:
                self._append_errors(key, 'set', ex.errors)
        else:
            self._append_errors(key, 'set', self.INVALID_COLLECTION_EXCEPTION)

    def _create_or_update_related_objects_add(self, data, key, data_item, model, current_values_list):
        if isinstance(data, (tuple, list)):
            try:
                return current_values_list + self._create_and_return_new_object_pk_list(data, model, self.inst)
            except DataInvalidException as ex:
                self._append_errors(key, 'add', ex.errors)
        else:
            self._append_errors(key, 'add', self.INVALID_COLLECTION_EXCEPTION)
        return current_values_list

    def _delete_objects_from_list(self, data, current_values_list, model):
        resource = self._get_resource(model)
        assert resource is not None

        errors = []
        result = [force_text(val) for val in current_values_list]
        i = 0
        for obj in data:
            try:
                pk = force_text(self._flat_object_to_pk(resource.pk_field_name, obj))
                if pk in result:
                    result.remove(pk)
                else:
                    errors.append({'error': _('Object does not exist in selected data'), '_index':i})
            except (DataInvalidException, RestException) as ex:
                rel_obj_errors = ex.errors
                rel_obj_errors['_index'] = i
                errors.append(rel_obj_errors)
            i += 1
        if errors:
            raise DataInvalidException(errors)
        return result

    def _create_or_update_objects_remove(self, data, key, data_item, model, current_values_list):
        if isinstance(data, (tuple, list)):
            try:
                return self._delete_objects_from_list(data, current_values_list, model)
            except DataInvalidException as ex:
                self._append_errors(key, 'remove', ex.errors)
        else:
            self._append_errors(key, 'remove', self.INVALID_COLLECTION_EXCEPTION)
        return current_values_list

    def _create_or_update_related_objects(self, data, key, data_item, model):
        resource = self._get_resource(model)
        if resource:
            if isinstance(data_item, (tuple, list)) or 'set' in data_item:
                set_data = isinstance(data_item, list) and data_item or data_item.get('set')
                data[key] = self._create_or_update_related_objects_set(set_data, key, data_item, model)

            else:
                field = self.form.fields.get(key)
                values = field.prepare_value(self.form.initial.get(key, field.initial)) or []

                if 'remove' in data_item:
                    values = self._create_or_update_objects_remove(data_item.get('remove'), key, data_item, model,
                                                                   values)
                if 'add' in data_item:
                    values = self._create_or_update_related_objects_add(data_item.get('add'), key,
                                                                         data_item, model, values)
                data[key] = values


    def _process_field(self, data, files, key, data_item):
        field = self.form.fields.get(key)
        if (field and isinstance(field, ModelMultipleChoiceField)
            and data_item and isinstance(data_item, (list, dict))):
            self._create_or_update_related_objects(data, key, data_item, field.queryset.model)


@data_postprocessors.register(BaseModelResource)
class ReverseMultipleDataPreprocessor(MultipleDataProcessorMixin, ResourceProcessorMixin, DataProcessor):

    def _create_or_update_reverse_related_objects_set(self, data, key, data_item, rel_object):
        resource = self._get_resource(rel_object.model)
        assert resource is not None

        if isinstance(data, (tuple, list)):
            try:
                new_object_pks = self._create_and_return_new_object_pk_list(data, rel_object.model, self.inst,
                                                                                 rel_object.field.name)
                # This is not optimal solution but is the most universal
                self._delete_reverse_objects(
                    resource._get_queryset().filter(**{rel_object.field.name: self.inst})
                     .exclude(pk__in=new_object_pks).values_list('pk', flat=True),
                     rel_object.model)
            except DataInvalidException as ex:
                self._append_errors(key, 'set', ex.errors)
        else:
            self._append_errors(key, 'set', self.INVALID_COLLECTION_EXCEPTION)

    def _create_or_update_reverse_related_objects_remove(self, data, key, data_item, rel_object):
        if isinstance(data, (tuple, list)):
            try:
                self._delete_reverse_objects(data, rel_object.model)
            except DataInvalidException as ex:
                self._append_errors(key, 'remove', ex.errors)
        else:
            self._append_errors(key, 'remove', self.INVALID_COLLECTION_EXCEPTION)

    def _create_or_update_reverse_related_objects_add(self, data, key, data_item, rel_object):
        if isinstance(data, (tuple, list)):
            try:
                self._create_and_return_new_object_pk_list(data, rel_object.model, self.inst,
                                                    rel_object.field.name)
            except DataInvalidException as ex:
                self._append_errors(key, 'add', ex.errors)
        else:
            self._append_errors(key, 'add', self.INVALID_COLLECTION_EXCEPTION)

    def _create_or_update_reverse_related_objects(self, data, key, data_item, model_descriptor):
        rel_object = model_descriptor.related
        resource = self._get_resource(rel_object.model)
        if resource:
            if isinstance(data_item, list) or 'set' in data_item:
                set_data_item = isinstance(data_item, list) and data_item or data_item.get('set')
                self._create_or_update_reverse_related_objects_set(set_data_item, key, data_item, rel_object)
            else:
                if 'remove' in data_item:
                    self._create_or_update_reverse_related_objects_remove(data_item.get('remove'), key,
                                                                          data_item, rel_object)
                if 'add' in data_item:
                    self._create_or_update_reverse_related_objects_add(data_item.get('add'), key,
                                                                       data_item, rel_object)

            try:
                del self.inst._prefetched_objects_cache[model_descriptor.related.field.related_query_name()]
            except (AttributeError, KeyError) as ex:
                pass

    def _process_field(self, data, files, key, data_item):
        model_descriptor = getattr(self.model, key, None)
        if (isinstance(model_descriptor, ForeignRelatedObjectsDescriptor) and ((isinstance(data_item, dict)
            and set(data_item.keys()).union({'set', 'add', 'remove'})) or (isinstance(data_item, list)))):
            self._create_or_update_reverse_related_objects(data, key, data_item, model_descriptor)


@data_postprocessors.register(BaseModelResource)
class ReverseDataPostprocessor(ResourceProcessorMixin, DataProcessor):

    def _create_or_update_single_reverse_related_objects(self, data, key, data_item, model_descriptor):
        rel_object = model_descriptor.related
        resource = self._get_resource(rel_object.model)
        if resource:
            related_obj = get_object_or_none(rel_object.model, **{rel_object.field.name:self.inst.pk})
            try:
                if data_item is None:
                    if related_obj:
                        self._delete_reverse_object({resource.pk_field_name: related_obj.pk}, rel_object.model)
                    setattr(self.inst, model_descriptor.cache_name, None)
                else:
                    if not isinstance(data_item, dict):
                        obj_data = {resource.pk_field_name: force_text(data_item)}
                    else:
                        obj_data = data_item.copy()

                    if not resource.pk_field_name in obj_data and related_obj:
                        obj_data[resource.pk_field_name] = related_obj.pk
                    obj_data[rel_object.field.name] = self.inst.pk
                    setattr(self.inst, key, self._create_or_update_related_object(obj_data, rel_object.model))

            except DataInvalidException as ex:
                self.errors[key] = ex.errors

    def _process_field(self, data, files, key, data_item):
        model_descriptor = getattr(self.model, key, None)
        if isinstance(model_descriptor, SingleRelatedObjectDescriptor):
            self._create_or_update_single_reverse_related_objects(data, key, data_item, model_descriptor)
