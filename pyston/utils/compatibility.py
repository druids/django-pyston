from __future__ import unicode_literals

import django
from django.template import Context
from django.template.loader import get_template
from django.core.exceptions import FieldError

try:
    from django.core.exceptions import FieldDoesNotExist
except ImportError:
    from django.db.models import FieldDoesNotExist


def get_field_from_model(model, field_name):
    if django.get_version() >= '1.8':
        return model._meta.get_field(field_name)
    else:
        return model._meta.get_field_by_name(field_name)[0]


def get_field_or_none(model, field_name):
    try:
        return get_field_from_model(model, field_name)
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


def get_model_from_related_descriptor(model_descriptor):
    return get_model_from_rel_obj(get_related_from_descriptior(model_descriptor))


def is_reverse_many_to_one(model, field_name):
    if django.get_version() >= '1.8':
        field = get_field_or_none(model, field_name)
        return field and field.auto_created and field.one_to_many
    else:
        from django.db.models.fields.related import ForeignRelatedObjectsDescriptor

        return isinstance(getattr(model, field_name, None), ForeignRelatedObjectsDescriptor)


def is_reverse_one_to_one(model, field_name):
    if django.get_version() >= '1.8':
        field = get_field_or_none(model, field_name)
        return field and field.auto_created and field.one_to_one
    else:
        from django.db.models.fields.related import SingleRelatedObjectDescriptor

        return isinstance(getattr(model, field_name, None), SingleRelatedObjectDescriptor)


def is_reverse_many_to_many(model, field_name):
    if django.get_version() >= '1.8':
        field = get_field_or_none(model, field_name)
        return field and field.auto_created and field.many_to_many
    else:
        from django.db.models.fields.related import ManyRelatedObjectsDescriptor

        return isinstance(getattr(model, field_name, None), ManyRelatedObjectsDescriptor)


def is_many_to_one(model, field_name):
    if django.get_version() >= '1.8':
        field = get_field_or_none(model, field_name)
        return field and not field.auto_created and field.many_to_one
    else:
        from django.db.models.fields.related import ForeignKey, OneToOneField

        field = getattr(getattr(model, field_name, None), 'field', None)
        return isinstance(field, ForeignKey) and not isinstance(field, OneToOneField)


def is_one_to_one(model, field_name):
    if django.get_version() >= '1.8':
        field = get_field_or_none(model, field_name)
        return field and not field.auto_created and field.one_to_one
    else:
        from django.db.models.fields.related import OneToOneField

        return isinstance(getattr(getattr(model, field_name, None), 'field', None), OneToOneField)


def is_many_to_many(model, field_name):
    if django.get_version() >= '1.8':
        field = get_field_or_none(model, field_name)
        return field and not field.auto_created and field.many_to_many
    else:
        from django.db.models.fields.related import ManyToManyField

        return isinstance(getattr(getattr(model, field_name, None), 'field', None), ManyToManyField)


def is_relation(model, field_name):
    return (
        is_one_to_one(model, field_name) or is_many_to_one(model, field_name) or is_many_to_many(model, field_name) or
        is_reverse_one_to_one(model, field_name) or is_reverse_many_to_one(model, field_name) or
        is_reverse_many_to_many(model, field_name)
    )


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


def get_model_from_relation(model, field_name):
    if is_many_to_many(model, field_name) or is_one_to_one(model, field_name) or is_many_to_one(model, field_name):
        return getattr(model, field_name).field.rel.to
    elif django.get_version() >= '1.9' and is_reverse_many_to_many(model, field_name):
        return getattr(model, field_name).field.model
    elif django.get_version() >= '1.9' and is_reverse_many_to_one(model, field_name):
        return getattr(model, field_name).field.model
    elif (django.get_version() >= '1.8' and (is_reverse_many_to_many(model, field_name) or
                                             is_reverse_one_to_one(model, field_name) or
                                             is_reverse_many_to_one(model, field_name))):
        return getattr(model, field_name).related.related_model
    elif (is_reverse_many_to_many(model, field_name) or is_reverse_one_to_one(model, field_name) or
            is_reverse_many_to_one(model, field_name)):
        return getattr(model, field_name).related.model
    else:
        raise FieldError('field {} is not relation'.format(field_name))


def get_model_from_relation_or_none(model, field_name):
    try:
        return get_model_from_relation(model, field_name)
    except FieldError:
        return None


def get_reverse_field_name(model, field_name):
    if is_many_to_many(model, field_name) or is_one_to_one(model, field_name) or is_many_to_one(model, field_name):
        return getattr(model, field_name).field.related_query_name()
    elif django.get_version() >= '1.9' and is_reverse_many_to_many(model, field_name):
        return getattr(model, field_name).field.name
    elif django.get_version() >= '1.9' and is_reverse_many_to_one(model, field_name):
        return getattr(model, field_name).field.name
    elif django.get_version() >= '1.8' and is_reverse_one_to_one(model, field_name):
        return getattr(model, field_name).related.field.name
    elif (is_reverse_many_to_many(model, field_name) or is_reverse_one_to_one(model, field_name) or
            is_reverse_many_to_one(model, field_name)):
        return getattr(model, field_name).related.field.name
    else:
        raise FieldError('field {} is not relation'.format(field_name))


def render_template(template_name, context):
    if django.get_version() < '1.9':
        context = Context(context)
    return get_template(template_name).render(context)
