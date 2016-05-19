from __future__ import unicode_literals

import django
from django.template import Context
from django.template.loader import get_template


def get_field_or_none(model, field_name):
    try:
        return model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return None


def get_model_from_rel_obj(rel_obj):
    if django.get_version() >= '1.8':
        return rel_obj.related_model
    else:
        return rel_obj.model


def get_all_related_objects_from_model(model):
    return model._meta.get_all_related_objects() if django.get_version() < '1.9' else [
        f for f in model._meta.get_fields()
        if (f.one_to_many or f.one_to_one) and f.auto_created
    ]


def get_related_from_descriptior(model_descriptor):
    if django.get_version() >= '1.9':
        print model_descriptor
        return getattr(model_descriptor, 'rel', getattr(model_descriptor, 'related', None))
    else:
        return model_descriptor.related


def get_model_from_related_descriptor(model_descriptor):
    return get_model_from_rel_obj(get_related_from_descriptior(model_descriptor))


def is_single_related_descriptor(model, field_name):
    if django.get_version() >= '1.8':
        field = get_field_or_none(model, field_name)
        return field and field.auto_created and field.one_to_one
    else:
        from django.db.models.fields.related import SingleRelatedObjectDescriptor

        return isinstance(getattr(model, field_name, None), SingleRelatedObjectDescriptor)


def is_multiple_related_descriptor(model, field_name):
    if django.get_version() >= '1.8':
        field = get_field_or_none(model, field_name)
        return field and field.auto_created and (field.many_to_many or field.one_to_many)
    else:
        from django.db.models.fields.related import ForeignRelatedObjectsDescriptor

        return isinstance(getattr(model, field_name, None), ForeignRelatedObjectsDescriptor)


def is_related_descriptor(model, field_name):
    return is_single_related_descriptor(model, field_name) or is_multiple_related_descriptor(model, field_name)


def render_template(template_name, context):
    if django.get_version() < '1.9':
        context = Context(context)
    return get_template(template_name).render(context)
