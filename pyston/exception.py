from django.utils.translation import ugettext_lazy as _


class UnsupportedMediaTypeException(Exception):
    """
    Raised if the content_type has unsupported media type
    """
    pass


class MimerDataException(Exception):
    """
    Raised if the content_type and data don't match
    """
    pass


class RestException(Exception):
    message = None

    def __init__(self, message=None):
        super().__init__()
        self.message = message or self.message

    @property
    def errors(self):
        return {'error': self.message}


class UnprocessableEntity(RestException):
    pass


class ResourceNotFoundException(RestException):
    message = _('Select a valid choice. That choice is not one of the available choices.')


class NotAllowedException(RestException):
    message = _('Not allowed.')


class UnauthorizedException(RestException):
    message = _('Unauthorized.')


class NotAllowedMethodException(RestException):
    message = _('Not allowed method.')


class DuplicateEntryException(RestException):
    message = _('Conflict/Duplicate.')


class ConflictException(RestException):
    message = _('Object already exists but you do not allowed to change it.')


class DataInvalidException(Exception):

    def __init__(self, errors):
        self.message = errors
        self.errors = errors
