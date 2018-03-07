import django
from django.template import Context
from django.template.loader import get_template
from django.core.exceptions import FieldError

from django.db.models import FieldDoesNotExist


def get_field_or_none(model, field_name):
    try:
        return model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return None


def get_all_related_objects_from_model(model):
    return [
        f for f in model._meta.get_fields()
        if (f.one_to_many or f.one_to_one) and f.auto_created and not f.concrete
    ]


def get_concrete_field(model, field_name):
    field = {
        f.name: f for f in model._meta.get_fields()
        if f.concrete and (not f.is_relation or f.one_to_one or (f.many_to_one and f.related_model))
    }.get(field_name)
    if field:
        return field
    else:
        raise FieldDoesNotExist


def is_reverse_many_to_one(model, field_name):
    field = get_field_or_none(model, field_name)
    return field and field.auto_created and field.one_to_many


def is_reverse_one_to_one(model, field_name):
    field = get_field_or_none(model, field_name)
    return field and field.auto_created and field.one_to_one


def is_reverse_many_to_many(model, field_name):
    field = get_field_or_none(model, field_name)
    return field and field.auto_created and field.many_to_many


def is_many_to_one(model, field_name):
    field = get_field_or_none(model, field_name)
    return field and not field.auto_created and field.many_to_one


def is_one_to_one(model, field_name):
    field = get_field_or_none(model, field_name)
    return field and not field.auto_created and field.one_to_one


def is_many_to_many(model, field_name):
    field = get_field_or_none(model, field_name)
    return field and not field.auto_created and field.many_to_many


def is_relation(model, field_name):
    return (
        is_one_to_one(model, field_name) or
        is_many_to_one(model, field_name) or
        is_many_to_many(model, field_name) or
        is_reverse_one_to_one(model, field_name) or
        is_reverse_many_to_one(model, field_name) or
        is_reverse_many_to_many(model, field_name)
    )


def get_model_from_relation(model, field_name):
    try:
        related_model = model._meta.get_field(field_name).related_model
        if related_model:
            return related_model
        else:
            raise FieldError('field {} is not relation'.format(field_name))
    except FieldDoesNotExist:
        raise FieldError('field {} is not relation'.format(field_name))


def get_model_from_relation_or_none(model, field_name):
    try:
        return get_model_from_relation(model, field_name)
    except FieldError:
        return None


def get_reverse_field_name(model, field_name):
    """
    Gets reverse field name, but for reverse fields must be set related_name,
    therefore must be check if it was set by getting reverse field from the reverse model
    """
    try:
        model_field = model._meta.get_field(field_name)
        reverse_field_name = model_field.remote_field.name
        model_field.related_model._meta.get_field(reverse_field_name)
        return reverse_field_name
    except (FieldDoesNotExist, AttributeError):
        raise FieldError('field {} is not relation'.format(field_name))


def get_last_parent_pk_field_name(obj):
    for field in obj._meta.fields:
        if field.primary_key and (not field.is_relation or not field.auto_created):
            return field.name
    raise RuntimeError('Last parent field name was not found (cannot happen)')


def delete_cached_value(instance, field_name):
    """
    Backward compatibility between django 1 and 2. Django 2 has helper for removing cached values via field.
    """
    field = instance._meta.get_field(field_name)
    if hasattr(field, 'is_cached'):
        if field.is_cached(instance):
            field.delete_cached_value(instance)
    else:
        setattr(instance, field.get_cache_name(), None)
