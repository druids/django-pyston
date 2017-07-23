class OrderError(Exception):
    pass


class OrderIdentifierError(OrderError):
    """
    Order exception that is raised if order identifier was not found.
    """
    pass
