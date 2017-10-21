from __future__ import unicode_literals

import binascii
import sys
import base64
import inspect
import mimetypes

from six import BytesIO

from django.forms.fields import FileField
from django.utils.translation import ugettext_lazy as _, ugettext
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from django.forms.models import ModelChoiceField, ModelMultipleChoiceField
from django.http.response import Http404
from django.utils.encoding import force_text

from chamber.shortcuts import get_object_or_none

from requests.exceptions import RequestException

from pyston.conf import settings as pyston_settings
from pyston.utils.compatibility import (
    is_reverse_one_to_one, is_reverse_many_to_one, is_reverse_many_to_many,
    get_reverse_field_name, get_model_from_relation
)
from pyston.utils.files import get_file_content_from_url, RequestDataTooBig

from .exception import DataInvalidException
from .resource import BaseObjectResource, BaseModelResource
from .forms import (
    ReverseField, ReverseSingleField, ReverseOneToOneField, ReverseStructuredManyField, SingleRelatedField,
    MultipleStructuredRelatedField, ReverseManyField, RESTFormMixin, RESTDictError, RESTError, RESTValidationError
)

url_validator = URLValidator()


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

    def __init__(self, resource, form, *args, **kwargs):
        self.resource = resource
        self.request = resource.request
        self.form = form

    def _process_field(self, data, files, key, data_item):
        raise NotImplementedError

    def _clear_data(self, data, files):
        return data, files

    def process_data(self, data, files):
        data, files = self._clear_data(data, files)

        self.errors = RESTDictError()
        for key, data_item in data.items():
            self._process_field(data, files, key, data_item)

        if self.errors:
            raise DataInvalidException(self.errors)
        return data, files


@data_preprocessors.register(BaseObjectResource)
class FileDataPreprocessor(DataProcessor):

    def _validate_not_empty(self, data_item, key, item):
        if not data_item.get(item):
            error = self.errors.get(key, {})
            error.update({item: ugettext('This field is required')})
            self.errors[key] = RESTDictError({key: RESTValidationError(error)})

    def _get_mimetype_from_filename(self, filename):
        return mimetypes.guess_type(filename)[0]

    def _get_content_type(self, data_item, filename):
        return data_item.get('content_type') or self._get_mimetype_from_filename(filename)

    def _process_file_data(self, data, files, key, data_item, file_content):
        filename = data_item.get('filename')
        content_type = self._get_content_type(data_item, filename)
        if content_type:
            charset = data_item.get('charset')
            files[key] = InMemoryUploadedFile(
                file_content, field_name=key, name=filename, content_type=content_type,
                size=sys.getsizeof(file_content), charset=charset
            )
            data[key] = filename
        else:
            self.errors[key] = RESTValidationError(ugettext(
                'Content type cannot be evaluated from the filename please send it or change the filename'
            ))

    def _process_file_data_field(self, data, files, key, data_item):
        try:
            file_content = BytesIO(base64.b64decode(data_item.get('content').encode('utf-8')))
            self._process_file_data(data, files, key, data_item, file_content)
        except (TypeError, binascii.Error):
            self.errors[key] = RESTDictError({'content': RESTValidationError(
                ugettext('File content must be in base64 format')
            )})

    def _process_file_data_url_field(self, data, files, key, data_item):
        url = data_item.get('url')
        try:
            file_content = get_file_content_from_url(url, pyston_settings.FILE_SIZE_LIMIT)
            self._process_file_data(data, files, key, data_item, file_content)
        except RequestDataTooBig:
            self.errors[key] = RESTDictError({'url': RESTValidationError(
                ugettext('Response too large, maximum size is {} bytes').format(
                    pyston_settings.FILE_SIZE_LIMIT
                ))
            })
        except RequestException:
            self.errors[key] = RESTDictError({'url': RESTValidationError(
                ugettext('File is unreachable on the URL address')
            )})
        try:
            url_validator(url)
        except ValidationError as e:
            self.errors[key] = RESTDictError({'url': RESTValidationError(e.messages[0])})

    def _process_field(self, data, files, key, data_item):
        field = self.form.fields.get(key)
        if field and isinstance(field, FileField) and isinstance(data_item, dict):
            REQUIRED_ITEMS = {'filename', 'content'}
            REQUIRED_URL_ITEMS = {'filename', 'url'}

            if REQUIRED_ITEMS.issubset(set(data_item.keys())):
                for item in REQUIRED_ITEMS:
                    self._validate_not_empty(data_item, key, item)

                if not self.errors:
                    self._process_file_data_field(data, files, key, data_item)
            elif REQUIRED_URL_ITEMS.issubset(set(data_item.keys())):
                for item in REQUIRED_URL_ITEMS:
                    self._validate_not_empty(data_item, key, item)

                if not self.errors:
                    self._process_file_data_url_field(data, files, key, data_item)
            else:
                self.errors[key] = RESTValidationError(
                    ugettext('File data item must contains {} or {}').format(
                        ', '.join(REQUIRED_ITEMS), ', '.join(REQUIRED_URL_ITEMS)
                    )
                )


class ModelResourceDataProcessor(DataProcessor):

    def __init__(self, resource, form, inst, via, partial_update):
        super(ModelResourceDataProcessor, self).__init__(resource, form)
        self.model = resource.model
        self.inst = inst
        self.via = resource._get_via(via)
        self.partial_update = partial_update

    def _get_resource_class(self, model):
        from .serializer import get_resource_class_or_none

        return get_resource_class_or_none(model, self.resource.resource_typemapper)


class MultipleDataProcessorMixin(object):

    INVALID_COLLECTION_EXCEPTION = {'error': _('Data must be a collection')}

    def _append_errors(self, key, operation, errors):
        self.errors[key] = self.errors.get(key, {})
        self.errors[key].update({operation: errors})


@data_preprocessors.register(BaseObjectResource)
class ModelDataPreprocessor(ModelResourceDataProcessor):

    def _process_field(self, data, files, key, data_item):
        rest_field = None
        form_field = self.form.fields.get(key)
        if (form_field and isinstance(form_field, ModelChoiceField) and
                not isinstance(form_field, ModelMultipleChoiceField)):
            resource_class = self._get_resource_class(form_field.queryset.model)
            rest_field = SingleRelatedField(self.form, key, resource_class) if resource_class else None

        if rest_field:
            try:
                data[key] = self.form.data[key] = rest_field.create_update_or_remove(
                    self.inst, data_item, self.via, self.request, self.partial_update, self.form
                )
            except RESTError as ex:
                self.errors[key] = ex


@data_preprocessors.register(BaseObjectResource)
class ModelMultipleDataPreprocessor(MultipleDataProcessorMixin, ModelResourceDataProcessor):

    def _process_field(self, data, files, key, data_item):
        rest_field = None
        form_field = self.form.fields.get(key)
        if form_field and isinstance(form_field, ModelMultipleChoiceField):
            resource_class = self._get_resource_class(form_field.queryset.model)
            rest_field = (
                MultipleStructuredRelatedField(self.form, key, resource_class) if resource_class else None
            )

        if rest_field:
            try:
                data[key] = self.form.data[key] = rest_field.create_update_or_remove(
                    self.inst, data_item, self.via, self.request, self.partial_update, self.form
                )
            except RESTError as ex:
                self.errors[key] = ex


@data_postprocessors.register(BaseModelResource)
class ReverseMultipleDataPostprocessor(MultipleDataProcessorMixin, ModelResourceDataProcessor):

    def _process_field(self, data, files, key, data_item):
        rest_field = getattr(self.form, key, None)
        if (not rest_field and isinstance(self.form, RESTFormMixin) and self.form._rest_meta.auto_reverse and (
                is_reverse_many_to_many(self.model, key) or is_reverse_many_to_one(self.model, key))):
            resource_class = self._get_resource_class(get_model_from_relation(self.model, key))
            rest_field = ReverseStructuredManyField(key, resource_class=resource_class) if resource_class else None
        if isinstance(rest_field, ReverseManyField):
            try:
                data[key] = self.form.data[key] = rest_field.create_update_or_remove(
                    self.inst, data_item, self.via, self.request, self.partial_update, self.form
                )
            except RESTError as ex:
                self.errors[key] = ex


@data_postprocessors.register(BaseModelResource)
class ReverseDataPostprocessor(ModelResourceDataProcessor):

    def _process_field(self, data, files, key, data_item):
        rest_field = getattr(self.form, key, None)
        if (not rest_field and isinstance(self.form, RESTFormMixin) and self.form._rest_meta.auto_reverse and
                is_reverse_one_to_one(self.model, key)):
            resource_class = self._get_resource_class(get_model_from_relation(self.model, key))
            rest_field = ReverseOneToOneField(key, resource_class=resource_class) if resource_class else None

        if isinstance(rest_field, ReverseSingleField):
            try:
                data[key] = self.form.data[key] = rest_field.create_update_or_remove(
                    self.inst, data_item, self.via, self.request, self.partial_update, self.form
                )
            except RESTError as ex:
                self.errors[key] = ex
