from __future__ import unicode_literals

import six

from chamber.patch import Options

import django.db.models.options as options
from django.db import models
from django.db.models.fields import Field, URLField
from django.db.models.fields.related import ForeignKey, ManyToManyField, ForeignObjectRel
from django.utils.translation import ugettext_lazy as _


from pyston.utils.compatibility import get_last_parent_pk_field_name


def merge_iterable(a, b):
    c = list(a) + list(b)
    return sorted(set(c), key=lambda x: c.index(x))


class RESTOptions(Options):

    model_class = models.Model
    meta_class_name = 'RESTMeta'
    meta_name = '_rest_meta'
    attributes = {}

    def __init__(self, model):
        super(RESTOptions, self).__init__(model)
        pk_field_name = get_last_parent_pk_field_name(model)

        fields = self._getattr('fields', ())

        self.default_fields = self._getattr('default_fields', (pk_field_name, '_obj_name'))
        self.detailed_fields = self._getattr('detailed_fields', fields)
        self.general_fields = self._getattr('general_fields', fields)
        self.direct_serialization_fields = self._getattr('direct_serialization_fields', fields)
        self.extra_fields = merge_iterable(
            self._getattr('extra_fields', ()),
            set(fields) - set(self.detailed_fields) - set(self.general_fields) - set(self.default_fields)
        )
        self.guest_fields = self._getattr('guest_fields', (pk_field_name, '_obj_name'))


options.DEFAULT_NAMES = options.DEFAULT_NAMES + ('default_fk_filter', 'default_m2m_filter', 'default_rel_filter')


def field_init(self, *args, **kwargs):
    _filter = kwargs.pop('filter', None)
    if _filter:
        self._filter = _filter
    self._init_is_core_tmp(*args, **kwargs)


def field_get_filter_class(self):
    return self._filter if hasattr(self, '_filter') else self.default_filter


def fk_get_filter_class(self):
    return (
        self._filter if hasattr(self, '_filter')
        else getattr(self.rel.to._meta, 'default_fk_filter', None) or self.default_filter
    )


def m2m_get_filter_class(self):
    return (
        self._filter if hasattr(self, '_filter')
        else getattr(self.rel.to._meta, 'default_m2m_filter', None) or self.default_filter
    )


def rel_get_filter_class(self):
    return getattr(self.field.model._meta, 'default_rel_filter', None) or self.default_filter


Field._init_is_core_tmp = Field.__init__
Field.__init__ = field_init
Field.filter = property(field_get_filter_class)

ForeignKey.filter = property(fk_get_filter_class)

ManyToManyField.filter = property(m2m_get_filter_class)

ForeignObjectRel.filter = property(rel_get_filter_class)

# because it is not translated in Django
_('(None)')