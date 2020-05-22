from pyston.utils import RFS


class RequestedFieldsParser:
    """
    Abstract fields parser.
    """

    def parse(self, request):
        """
        :param request: Django HTTP request.
        :return: returns RFS objects..
        """
        raise NotImplementedError


class DefaultRequestedFieldsParser:
    """
    Default fields parserr.
    E.q.:
        /api/user?_filter=first_name,last_name,issues(id)
    """

    def parse(self, request):
        input = request._rest_context.get('fields')
        if input is None:
            return None
        return RFS.create_from_string(input)
