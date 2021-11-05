# Apply patch only if django is installed
try:
    from django.core.exceptions import ImproperlyConfigured
    try:
        from django.db import models  # noqa: F401
        from pyston import patch  # noqa: F401
    except ImproperlyConfigured:
        pass
except ImportError:
    pass
