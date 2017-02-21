from django.conf import settings as django_settings


CONVERTERS = (
    'pyston.converters.JSONConverter',
    'pyston.converters.XMLConverter',
    'pyston.converters.CSVConverter',
)

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
    'JSON_CONVERTER_OPTIONS': {
        'indent': 4
    },
    'PDF_EXPORT_TEMPLATE': 'default_pdf_table.html',
}


class Settings(object):

    def __getattr__(self, attr):
        if attr not in DEFAULTS:
            raise AttributeError('Invalid Pyston setting: "{}"'.format(attr))

        return getattr(django_settings, 'PYSTON_{}'.format(attr), DEFAULTS[attr])


settings = Settings()
