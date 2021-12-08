import types
import sys

from io import BytesIO

import datetime
import decimal
import uuid

from django.utils.encoding import force_bytes
from django.conf import settings
from django.utils.duration import duration_iso_string
from django.utils.functional import Promise
from django.utils.timezone import is_aware

from chamber.utils import get_class_method

from .compatibility import FieldDoesNotExist


class ModelIteratorHelper:

    def __init__(self, model):
        self.model = model

    def __iter__(self):
        raise NotImplementedError


class ModelIterableIteratorHelper(ModelIteratorHelper):

    def __init__(self, iterable, model):
        super().__init__(model)
        self.iterable = iterable

    def __iter__(self):
        return iter(self.iterable)


class UniversalBytesIO:

    def __init__(self, container=None, charset=None):
        self.charset = charset or settings.DEFAULT_CHARSET
        self._container = BytesIO() if container is None else container

    # These methods partially implement the file-like object interface.
    # See https://docs.python.org/3/library/io.html#io.IOBase

    def close(self):
        self._container.close()

    def write(self, content):
        self._container.write(self.make_bytes(content))

    def flush(self):
        self._container.flush()

    def tell(self):
        return self._container.tell()

    def readable(self):
        return False

    def seekable(self):
        return False

    def writable(self):
        return True

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def make_bytes(self, value):
        """Turn a value into a bytestring encoded in the output charset."""
        if isinstance(value, bytes):
            return bytes(value)
        if isinstance(value, str):
            return bytes(value.encode(self.charset))

        # Handle non-string types
        return force_bytes(value, self.charset)

    def getvalue(self):
        return self._container.getvalue().decode(self.charset)

    if sys.version_info[0:2] < (3, 5):
        def seek(self, *args, **kwargs):
            pass


def serialized_data_to_python(data):
    from pyston.serializer import LAZY_SERIALIZERS

    if isinstance(data, (types.GeneratorType, list, tuple)):
        return [serialized_data_to_python(val) for val in data]
    elif isinstance(data, LAZY_SERIALIZERS):
        return serialized_data_to_python(data.serialize())
    elif isinstance(data, dict):
        return {key: serialized_data_to_python(val) for key, val in data.items()}
    if isinstance(data, datetime.datetime):
        r = data.isoformat()
        if data.microsecond:
            r = r[:23] + r[26:]
        if r.endswith('+00:00'):
            r = r[:-6] + 'Z'
        return r
    elif isinstance(data, datetime.date):
        return data.isoformat()
    elif isinstance(data, datetime.time):
        if is_aware(data):
            raise ValueError("JSON can't represent timezone-aware times.")
        r = data.isoformat()
        if data.microsecond:
            r = r[:12]
        return r
    elif isinstance(data, datetime.timedelta):
        return duration_iso_string(data)
    elif isinstance(data, (decimal.Decimal, uuid.UUID, Promise)):
        return str(data)
    else:
        return data


def str_to_class(class_string):
    module_name, class_name = class_string.rsplit('.', 1)
    # load the module, will raise ImportError if module cannot be loaded
    m = __import__(module_name, globals(), locals(), str(class_name))
    # get the class, will raise AttributeError if class cannot be found
    c = getattr(m, class_name)
    return c


def get_field_or_none(model, field_name):
    try:
        return model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return None


def get_method_or_none(model, name):
    try:
        return get_class_method(model, name)
    except (AttributeError, FieldDoesNotExist):
        return None
