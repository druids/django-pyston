import os
import requests

import cgi
import mimetypes

import magic  # pylint: disable=E0401

from io import BytesIO

from django.core.exceptions import SuspiciousOperation

from pyston.conf import settings


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


def get_content_type_from_filename(filename):
    return mimetypes.guess_type(filename)[0]


def get_content_type_from_file_content(content):
    with magic.Magic(flags=magic.MAGIC_MIME_TYPE) as m:
        mime_type = m.id_buffer(content.read(1024))
        content.seek(0)
        return mime_type


def get_filename_from_content_type(content_type):
    extensions = mimetypes.guess_all_extensions(content_type)
    known_extensions = [ext for exts, name in settings.DEFAULT_FILENAMES for ext in exts]
    extensions.sort(
        key=lambda x: known_extensions.index(x[1:]) if x[1:] in known_extensions else len(known_extensions)
    )
    extension = extensions[0] if extensions else None

    if extension:
        default_filenames = {ext: name for exts, name in settings.DEFAULT_FILENAMES for ext in exts}
        filename = default_filenames.get(extension[1:], settings.DEFAULT_FILENAME)
        return '{}{}'.format(filename, extension)
    else:
        return None


def get_file_name_type_and_content_from_url(url, limit, timeout=1):
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

    params = cgi.parse_header(resp.headers.get('Content-Disposition', ''))[-1]
    filename = os.path.basename(params['filename']) if 'filename' in params else None
    content_type = resp.headers.get('Content-Type', None)

    return filename, content_type, content
