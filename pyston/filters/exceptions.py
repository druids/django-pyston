class FilterError(Exception):
    pass


class OperatorFilterError(FilterError):
    """
    Filter exception that is raised if operator is not allowed.
    """
    pass


class FilterValueError(FilterError):
    """
    Filter exception that is raised if value has invalid format.
    """
    pass


class FilterIdentifierError(FilterError):
    """
    Filter exception that is raised if filter identifier was not found.
    """
    pass
