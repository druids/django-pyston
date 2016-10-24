from __future__ import unicode_literals

from django.db import models
from django.db.models.fields import Field

from chamber.patch import Options, OptionsLazy


class RESTOptions(Options):

    model_class = models.Model
    meta_class_name = 'RESTMeta'
    meta_name = '_rest_meta'
    attributes = {
        'default_detailed_fields': {'id', '_obj_name', '_rest_links'},
        'default_general_fields': {'id', '_obj_name', '_rest_links'},
        'direct_serialization_fields': {'id'},
        'extra_fields': {},
        'guest_fields': {'id'},
    }


def field_init(self, *args, **kwargs):
    humanize_func = kwargs.pop('humanized', None)
    if humanize_func:
        def humanize(val, inst, *args, **kwargs):
            humanize_func(self, val, inst, *args, **kwargs)
        self.humanized = humanize
    else:
        self.humanized = None
    self._init_pyston_tmp(*args, **kwargs)


Field._init_pyston_tmp = Field.__init__
Field.__init__ = field_init