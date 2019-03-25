from django.core.exceptions import ValidationError
from django.contrib.postgres.utils import prefix_validation_error
from django.contrib.postgres.forms.array import SimpleArrayField
from django.utils.translation import ugettext


class RESTSimpleArrayField(SimpleArrayField):
    """
    Django array form field doesn't accept list. Therefore we must rewrite to_python method
    """

    def to_python(self, value):
        if value is None:
            return None

        if isinstance(value, list):
            errors = []
            values = []
            for index, item in enumerate(value):
                try:
                    values.append(self.base_field.to_python(item))
                except ValidationError as error:
                    errors.append(prefix_validation_error(
                        error,
                        prefix=self.error_messages['item_invalid'],
                        code='item_invalid',
                        params={'nth': index},
                    ))
            if errors:
                raise ValidationError(errors)
        else:
            raise ValidationError(ugettext('Enter a list.'))
        return values

    def clean(self, value):
        if value is None:
            return value
        else:
            return super().clean(value)
