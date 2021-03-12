from django.utils.encoding import force_text
from django.db import models
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.template.defaultfilters import capfirst
from django.forms.utils import pretty_name

from chamber.utils import get_class_method

from collections import OrderedDict

from pyston.utils import split_fields, is_match, get_model_from_relation_or_none, LOOKUP_SEP, rfs
from pyston.utils.compatibility import get_all_related_objects_from_model, get_concrete_field, get_model_from_relation


class Field:

    def __init__(self, key_path, label):
        self.key_path = key_path
        self.label = label

    def __str__(self):
        return capfirst(
            self.label if self.label is not None
            else pretty_name(' - '.join([key.replace('_', ' ').strip() for key in self.key_path]))
        )

    def __hash__(self):
        return hash(LOOKUP_SEP.join(self.key_path))

    def __eq__(self, other):
        return self.__str__() == other.__str__()

    def __ne__(self, other):
        return not self.__eq__(other)


class FieldsetGenerator:

    def __init__(self, resource=None, fields_string=None, direct_serialization=False):
        self.resource = resource
        self.fields_string = fields_string
        self.direct_serialization = direct_serialization

    def _get_resource(self, obj):
        from pyston.serializer import get_resource_or_none

        if self.resource:
            return get_resource_or_none(self.resource.request, obj, self.resource.resource_typemapper)
        else:
            return None

    def _get_allowed_fieldset(self):
        from pyston.resource import DefaultRESTObjectResource

        # For security reasons only resource which defines allowed fields can be fully converted to the CSV/XLSX
        # or similar formats
        return self.resource.get_allowed_fields_rfs() if isinstance(self.resource, DefaultRESTObjectResource) else rfs()

    def _parse_fields_string(self, fields_string):
        fields_string = fields_string or ''

        parsed_fields = []
        for field in split_fields(fields_string):
            if LOOKUP_SEP in field:
                field_name, subfields_string = field.split(LOOKUP_SEP, 1)
            elif is_match('^[^\(\)]+\(.+\)$', field):
                field_name, subfields_string = field[:len(field) - 1].split('(', 1)
            else:
                field_name, subfields_string = field, None

            parsed_fields.append((field_name, subfields_string))
        return parsed_fields

    def _recursive_generator(self, fields, fields_string, model=None, key_path=None, extended_fieldset=None):
        key_path = key_path or []

        allowed_fieldset = self._get_allowed_fieldset()
        if extended_fieldset:
            allowed_fieldset.join(extended_fieldset)

        parsed_fields = [
            (field_name, subfields_string) for field_name, subfields_string in self._parse_fields_string(fields_string)
            if field_name in allowed_fieldset or self.direct_serialization
        ]

        for field_name, subfields_string in parsed_fields:
            self._recursive_generator(
                fields, subfields_string, get_model_from_relation_or_none(model, field_name) if model else None,
                key_path + [field_name],
                extended_fieldset=allowed_fieldset[field_name].subfieldset if allowed_fieldset[field_name] else None
            )
        if not parsed_fields and key_path:
            fields.append(
                Field(key_path, self.resource.get_field_label(LOOKUP_SEP.join(key_path)) if self.resource else None)
            )

    def generate(self):
        fields = []
        self._recursive_generator(fields, self.fields_string, getattr(self.resource, 'model', None))
        return fields
