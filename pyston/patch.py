from __future__ import unicode_literals

from django.db import models

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
