import requests

from six import BytesIO

from django.core.exceptions import SuspiciousOperation


def request(method, url, **kwargs):
    try:
        from security.transport.security_requests import request

        kwargs['slug'] = 'Pyston - file download'
    except ImportError:
        from requests import request

    return request(method, url, **kwargs)


class RequestDataTooBig(SuspiciousOperation):
    pass


class InvalidResponseStatusCode(SuspiciousOperation):
    pass


def get_file_content_from_url(url, limit, timeout=1):
    resp = request('get', url, timeout=timeout, stream=True)

    content = BytesIO()
    length = 0

    if resp.status_code != 200:
        raise InvalidResponseStatusCode('Invalid response status code "{}"'.format(resp.status_code))

    for chunk in resp.iter_content(2048):
        content.write(chunk)
        length += len(chunk)
        if length > limit:
            resp.close()
            raise RequestDataTooBig('Requested file is too big')

    content.seek(0)

    return content
