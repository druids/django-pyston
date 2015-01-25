from django.utils.datastructures import SortedDict
from django.utils.encoding import force_text
from django.db import models
from django.db.models.fields import FieldDoesNotExist
from django.core.exceptions import ObjectDoesNotExist
from django.template.defaultfilters import capfirst

from collections import OrderedDict


class ModelSortedDict(OrderedDict):

    def __init__(self, model, resource, *args, **kwargs):
        super(ModelSortedDict, self).__init__(*args, **kwargs)
        self.model = model
        self.resource = resource


class Field(object):

    def __init__(self, key_path, label_path):
        self.key_path = key_path
        self.label_path = label_path

    def __str__(self):
        return ' '.join(map(force_text, self.label_path))

    def __unicode__(self):
        return capfirst(' '.join(map(force_text, self.label_path)))

    def __hash__(self):
            return hash('__'.join(self.key_path))

    def __eq__(self, other):
        return self.__str__() == other.__str__()

    def __ne__(self, other):
        return not self.__eq__(other)


class Fieldset(object):

    @classmethod
    def create_from_data(cls, data):
        fieldset = Fieldset()
        fieldset._init_data(data)
        return fieldset

    @classmethod
    def create_from_string(cls, str_fieldset):
        fieldset = Fieldset()
        fieldset._init_string(str_fieldset)
        return fieldset

    def __init__(self):
        self.root = {}
        self.fieldset = SortedDict()

    def _tree_contains(self, field):
        current = self.root.get(field.key_path[0])
        if current is None:
            return False

        for key in field.key_path[1:]:
            if not current:
                return True
            elif key not in current.keys():
                return False
            else:
                current = current.get(key)

        return not bool(current)

    def _remove_childs(self, key_path, tree):
        if not tree:
            del self.fieldset['__'.join(key_path)]
        else:
            for key, subtree in tree.items():
                self._remove_childs(key_path + [key], subtree)

    def add(self, field):
        if not self._tree_contains(field):
            current = self.root
            for key in field.key_path:
                current[key] = current.get(key, {})
                prev = current
                current = current[key]

            if current:
                self._remove_childs(field.key_path, current)

            prev[key] = {}
            self.fieldset['__'.join(field.key_path)] = field

    def union(self, iterable):
        for item in iterable:
            self.add(item)

    def _get_field_label_from_model_related_objects(self, model, field_name):
        for rel in model._meta.get_all_related_objects():
            reverse_name = rel.get_accessor_name()
            if field_name == reverse_name:
                if isinstance(rel.field, models.OneToOneField):
                    return rel.model._meta.verbose_name
                else:
                    return rel.model._meta.verbose_name_plural
        return None

    def _get_field_label_from_resource_or_model_method(self, resource_or_model, field_name):
        return getattr(resource_or_model, field_name).short_description

    def _get_field_label_from_model_field(self, model, field_name):
        return model._meta.get_field(field_name).verbose_name

    def _get_field_label_from_model(self, model, resource, field_name):
        try:
            return self._get_field_label_from_model_field(model, field_name)
        except FieldDoesNotExist:
            for resource_or_model in [resource, model]:
                try:
                    return self._get_field_label_from_resource_or_model_method(resource_or_model, field_name)
                except (AttributeError, ObjectDoesNotExist):
                    pass
            return self._get_field_label_from_model_related_objects(model, field_name)

    def _init_data(self, converted_data, key_path=None, label_path=None):
        key_path = key_path or []
        label_path = label_path or []

        if isinstance(converted_data, dict):
            for key, val in converted_data.items():
                if isinstance(converted_data, ModelSortedDict):
                    label = (self._get_field_label_from_model(converted_data.model, converted_data.resource, key) or
                               (key != '_obj_name' and key or '')
                             )
                else:
                    label = key
                self._init_data(val, list(key_path) + [key], list(label_path) + [label])
        elif isinstance(converted_data, (list, tuple, set)):
            is_last_list = False
            for val in converted_data:
                if isinstance(list, (list, tuple, set)):
                    is_last_list = True
                    break
                self._init_data(val, list(key_path), list(label_path))
            if is_last_list:
                self.add(Field(key_path, label_path, label_path))
        elif converted_data is not None:
            self.add(Field(key_path, label_path))

    def _init_string(self, str_fieldset, key_path=None, label_path=None):
        for field in str_fieldset.split(','):
            self.fieldset[field] = Field(field, field)

    def __iter__(self):
        return iter(self.fieldset.values())

    def __contains__(self, field):
        if isinstance(field, Field):
            return '__'.join(field.key_path) in self.fieldset
        else:
            return field in self.fieldset

    def __nonzero__(self):
        return bool(self.fieldset)

    def __str__(self):
        return '{%s}' % ', '.join(self.fieldset.values())

    def __len__(self):
        return len(self.fieldset)
