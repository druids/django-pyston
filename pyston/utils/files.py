import requests
from six import BytesIO

from django.core.exceptions import SuspiciousOperation, ValidationError
from django.core.validators import URLValidator


url_validator = URLValidator()


class RequestDataTooBig(SuspiciousOperation):
    pass


def get_file_content_from_url(url, limit, timeout=1):
    url_validator(url)
    resp = requests.get(url, timeout=timeout, stream=True)

    content = BytesIO()
    length = 0

    for chunk in resp.iter_content(2048):
        content.write(chunk)
        length += len(chunk)
        if length > limit:
            resp.close()
            raise RequestDataTooBig('Requested file is too big')

    content.seek(0)

    return content
