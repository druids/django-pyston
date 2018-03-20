from pyston.utils import LOOKUP_SEP

from .utils import DIRECTION


class OrderParserError(Exception):
    """
    Exception that is raised if order input is invalid.
    """
    pass


class OrderTerm:
    """
    Simple order term that contains order identifiers list, direction and source inpout value which is used to assemble
    error messages.
    """

    def __init__(self, identifiers, direction, source):
        self.identifiers = identifiers
        self.direction = direction
        self.source = source


class OrderParser:
    """
    Abstract order parser.
    """

    def parse(self, request):
        """
        :param request: Django HTTP request.
        :return: returns list of order terms.
        """
        raise NotImplementedError


class DefaultOrderParser:
    """
    Default order parser that accepts filter.
    E.q.:
        /api/user?order=first_name,-created_at
    """

    def _clean_order_term(self, ordering_string):
        ordering_string = ordering_string.strip()
        if ordering_string.startswith('-'):
            direction = DIRECTION.DESC
            ordering_string = ordering_string[1:]
        else:
            direction = DIRECTION.ASC

        identifiers = ordering_string.split(LOOKUP_SEP)
        return OrderTerm(identifiers, direction, ordering_string)

    def parse(self, request):
        order_fields = request._rest_context.get('order')
        if order_fields:
            return (self._clean_order_term(ordering_string) for ordering_string in order_fields.split(','))
        else:
            return None
