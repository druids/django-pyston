from django.conf import settings as django_settings


CONVERTERS = (
    'pyston.converters.JSONConverter',
    'pyston.converters.XMLConverter',
    'pyston.converters.CSVConverter',
    'pyston.converters.TXTConverter',
)

DEFAULT_FILENAMES = (
    (('pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv'), 'document'),
    (('jpg', 'jpeg', 'png', 'gif', 'tiff', 'bmp', 'svg'), 'image'),
)

DEFAULT_FILENAME = 'attachment'

try:
    import xlsxwriter

    CONVERTERS += (
        'pyston.converters.XLSXConverter',
    )
except ImportError:
    pass

try:
    # pisa isn't standard with python. It shouldn't be required if it isn't used.
    from xhtml2pdf import pisa

    CONVERTERS += (
        'pyston.converters.PDFConverter',
    )
except ImportError:
    pass


DEFAULTS = {
    'CONVERTERS': CONVERTERS,
    'IGNORE_DUPE_MODELS': False,
    'CORS': False,
    'CORS_WHITELIST': (),
    'CORS_MAX_AGE': 60 * 30,
    'CORS_ALLOW_CREDENTIALS': True,
    'CORS_ALLOWED_HEADERS': ('X-Base', 'X-Offset', 'X-Fields', 'Origin', 'Content-Type', 'Accept'),
    'CORS_ALLOWED_EXPOSED_HEADERS': ('X-Total', 'X-Serialization-Format-Options', 'X-Fields-Options'),
    'JSON_CONVERTER_OPTIONS': {
        'indent': 4
    },
    'PDF_EXPORT_TEMPLATE': 'default_pdf_table.html',
    'FILE_SIZE_LIMIT': 5000000,
    'AUTO_RELATED_REVERSE_FIELDS': True,
    'AUTO_RELATED_DIRECT_FIELDS': True,
    'PARTIAL_PUT_UPDATE': False,
    'PARTIAL_RELATED_UPDATE': False,
    'ERRORS_RESPONSE_CLASS': 'pyston.response.RESTErrorsResponse',
    'ERROR_RESPONSE_CLASS': 'pyston.response.RESTErrorResponse',
    'AUTO_REGISTER_RESOURCE': True,
    'ALLOW_TAGS': False,
    'DEFAULT_FILENAMES': DEFAULT_FILENAMES,
    'DEFAULT_FILENAME': DEFAULT_FILENAME,
    'NONE_HUMANIZED_VALUE': '--',
}


class Settings:

    def __getattr__(self, attr):
        if attr not in DEFAULTS:
            raise AttributeError('Invalid Pyston setting: "{}"'.format(attr))

        return getattr(django_settings, 'PYSTON_{}'.format(attr), DEFAULTS[attr])


settings = Settings()
