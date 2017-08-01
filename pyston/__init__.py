# Apply patch only if django is installed
try:
    from django.core.exceptions import ImproperlyConfigured
    try:
        from django.db import models  # NOQA
        from pyston.patch import *  # NOQA
        from pyston.filters.default_filters import * # NOQA
    except ImproperlyConfigured:
        pass
except ImportError as ex:
    pass
