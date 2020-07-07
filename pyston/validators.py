from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy


class ISODateTimeValidator(RegexValidator):

    def __init__(self):
        super().__init__(
            regex=r'^(-?(?:[1-9][0-9]*)?[0-9]{4})-(1[0-2]|0[1-9])-(3[01]|0[1-9]|[12][0-9])T(2[0-3]|[01][0-9]):'
                  r'([0-5][0-9]):([0-5][0-9])(\.[0-9]+)?(Z|[+-](?:2[0-3]|[01][0-9]):[0-5][0-9])?$',
            message=gettext_lazy('Enter a valid date/time.')
        )
