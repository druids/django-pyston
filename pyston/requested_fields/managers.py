from pyston.exception import RESTException
from pyston.utils import rfs

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
        except RESTException as ex:
            raise RESTException(ex)


class DefaultRequestedFieldsManager(ModelRequestedFieldsManager):
    """
    Default requested fields manager.
    """

    parser = DefaultRequestedFieldsParser()
