from chamber.patch import Options

import django.db.models.options as options
from django.db import models
from django.db.models.fields import Field
from django.db.models.fields.related import ForeignKey, ManyToManyField, ForeignObjectRel

from pyston.utils.compatibility import get_last_parent_pk_field_name


def merge_iterable(a, b):
    c = list(a) + list(b)
    return sorted(set(c), key=lambda x: c.index(x))


class RestOptions(Options):

    model_class = models.Model
    meta_class_name = 'RestMeta'
    meta_name = '_rest_meta'
    attributes = {}

    def __init__(self, model):
        super().__init__(model)
        pk_field_name = get_last_parent_pk_field_name(model)

        fields = self._getattr('fields', ())

        self.default_fields = self._getattr('default_fields', (pk_field_name,))
        self.detailed_fields = self._getattr('detailed_fields', fields)
        self.general_fields = self._getattr('general_fields', fields)
        self.direct_serialization_fields = self._getattr('direct_serialization_fields', fields)
        self.extra_fields = merge_iterable(
            self._getattr('extra_fields', ()),
            set(fields) - set(self.detailed_fields) - set(self.general_fields) - set(self.default_fields)
        )
        self.guest_fields = self._getattr('guest_fields', (pk_field_name,))
        self.filter_fields = self._getattr('filter_fields', None)
        self.order_fields = self._getattr('order_fields', None)
        self.extra_filter_fields = self._getattr('extra_filter_fields', ())
        self.extra_order_fields = self._getattr('extra_order_fields', ())


options.DEFAULT_NAMES = options.DEFAULT_NAMES + ('default_fk_filter', 'default_m2m_filter', 'default_rel_filter')


def field_init(self, *args, **kwargs):
    _filter = kwargs.pop('filter', None)
    if _filter:
        self._filter = _filter
    self._init_pyston_tmp(*args, **kwargs)


def field_get_filter_class(self):
    return self._filter if hasattr(self, '_filter') else None


def fk_get_filter_class(self):
    return (
        self._filter if hasattr(self, '_filter')
        else getattr(self.related_model._meta, 'default_fk_filter', None)
    )


def m2m_get_filter_class(self):
    return (
        self._filter if hasattr(self, '_filter')
        else getattr(self.related_model._meta, 'default_m2m_filter', None)
    )


def rel_get_filter_class(self):
    return getattr(self.field.model._meta, 'default_rel_filter', None)


Field._init_pyston_tmp = Field.__init__
Field.__init__ = field_init
Field.filter = property(field_get_filter_class)

ForeignKey.filter = property(fk_get_filter_class)

ManyToManyField.filter = property(m2m_get_filter_class)

ForeignObjectRel.filter = property(rel_get_filter_class)
