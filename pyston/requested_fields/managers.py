from pyston.exception import RestException

from .parser import DefaultRequestedFieldsParser


class ModelRequestedFieldsManager:

    parser = None

    def get_requested_fields(self, resource, request):
        try:
            parsed_requested_rfs = self.parser.parse(request)
            if parsed_requested_rfs is None:
                return None
            else:
                return parsed_requested_rfs
        except RestException as ex:
            raise RestException(ex)


class DefaultRequestedFieldsManager(ModelRequestedFieldsManager):
    """
    Default requested fields manager.
    """

    parser = DefaultRequestedFieldsParser()
