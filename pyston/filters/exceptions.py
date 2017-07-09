class FilterException(Exception):
    pass


class OperatorFilterException(FilterException):
    pass


class FilterValueException(FilterException):
    pass


class FilterIdentifierException(FilterException):
    pass
