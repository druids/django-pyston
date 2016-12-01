from __future__ import unicode_literals

from django.db import models
from django.db.models.fields import Field

from chamber.patch import Options

from pyston.utils.compatibility import get_last_parent_pk_field_name


class RESTOptions(Options):

    model_class = models.Model
    meta_class_name = 'RESTMeta'
    meta_name = '_rest_meta'

    def _get_attributes(self, model):
        pk_field_name = get_last_parent_pk_field_name(model)
        return {
            'default_detailed_fields': {pk_field_name, '_obj_name', '_rest_links'},
            'default_general_fields': {pk_field_name, '_obj_name', '_rest_links'},
            'direct_serialization_fields': {pk_field_name},
            'extra_fields': {},
            'guest_fields': {pk_field_name},
        }


def field_init(self, *args, **kwargs):
    humanize_func = kwargs.pop('humanized', None)
    if humanize_func:
        def humanize(val, inst, *args, **kwargs):
            return humanize_func(val, inst, field=self, *args, **kwargs)
        self.humanized = humanize
    else:
        self.humanized = None
    self._init_pyston_tmp(*args, **kwargs)


Field._init_pyston_tmp = Field.__init__
Field.__init__ = field_init
