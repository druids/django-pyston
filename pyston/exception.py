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


class RESTException(Exception):
    message = None

    def __init__(self, message=None):
        super(RESTException, self).__init__()
        self.message = message or self.message

    @property
    def errors(self):
        return {'error': self.message}


class ResourceNotFoundException(RESTException):
    message = _('Select a valid choice. That choice is not one of the available choices.')


class NotAllowedException(RESTException):
    message = _('Not allowed.')


class UnauthorizedException(RESTException):
    message = _('Unauthorized.')


class NotAllowedMethodException(RESTException):
    message = _('Not allowed method.')


class DuplicateEntryException(RESTException):
    message = _('Conflict/Duplicate.')


class ConflictException(RESTException):
    message = _('Object already exists but you do not allowed to change it.')


class DataInvalidException(Exception):

    def __init__(self, errors):
        self.message = errors
        self.errors = errors
