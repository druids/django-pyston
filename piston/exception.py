class UnsupportedMediaTypeException(Exception):
    """
    Raised if the content_type has unssopported media type
    """
    pass


class MimerDataException(Exception):
    """
    Raised if the content_type and data don't match
    """
    pass
