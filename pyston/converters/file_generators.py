import os

import csv
import codecs

from io import StringIO

from datetime import datetime, date
from decimal import Decimal

from django.conf import settings as django_settings
from django.utils.encoding import force_text
from django.template.loader import get_template

try:
    # xlsxwriter isn't standard with python.  It shouldn't be required if it
    # isn't used.
    import xlsxwriter
except ImportError:
    xlsxwriter = None
    XLSXGenerator = None


try:
    # pisa isn't standard with python. It shouldn't be required if it isn't used.
    from xhtml2pdf import pisa
except ImportError:
    pisa = None
    PDFGenerator = None

from pyston.conf import settings


TWOPLACES = Decimal(10) ** -2


class CSVGenerator:

    def __init__(self, delimiter=chr(59), quotechar=chr(34), quoting=csv.QUOTE_ALL, encoding='utf-8'):
        self.encoding = encoding
        self.quotechar = quotechar
        self.quoting = quoting
        self.delimiter = delimiter

    def generate(self, header, data, output_stream):
        writer = StreamCSV(output_stream, delimiter=self.delimiter, quotechar=self.quotechar, quoting=self.quoting)

        if header:
            writer.writerow(self._prepare_list(header))

        for row in data:
            writer.writerow(self._prepare_list(row))

    def _prepare_list(self, values):
        prepared_row = []

        for value in values:
            value = self._prepare_value(value.get('value') if isinstance(value, dict) else value)
            prepared_row.append(value)
        return prepared_row

    def _prepare_value(self, value):
        if isinstance(value, float):
            value = ('%.2f' % value).replace('.', ',')
        elif isinstance(value, Decimal):
            value = force_text(value.quantize(TWOPLACES)).replace('.', ',')
        else:
            value = force_text(value)
        return value.replace('&nbsp;', ' ')


class StreamCSV:

    def __init__(self, f, dialect=csv.excel, **kwds):
        self.writer = csv.writer(f, dialect=dialect, **kwds)
        self.stream = f
        self.stream.write(force_text(codecs.BOM_UTF8))  # BOM for Excel

    def writerow(self, row):
        self.writer.writerow(row)
        self.stream.flush()

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


class TXTGenerator:

    def _prepare_value(self, value):
        return value.replace('&nbsp;', ' ')

    def generate(self, header, data, output_stream):
        output_stream.write('---\n')
        for data_row in data:
            output_stream.write('\n')
            for col, val in enumerate(data_row):
                if header:
                    output_stream.write('{}:\n'.format(header[col]))
                if isinstance(val, str):
                    val = self._prepare_value(val)
                output_stream.write('\t'.join(('\t' + force_text(val).lstrip()).splitlines(True)) + '\n\n')
            output_stream.write('---\n')


if xlsxwriter:
    class XLSXGenerator:

        def _prepare_value(self, value):
            return value.replace('&nbsp;', ' ')

        def generate(self, header, data, output_stream):
            wb = xlsxwriter.Workbook(output_stream)
            ws = wb.add_worksheet()

            date_format = wb.add_format({'num_format': 'd. mmmm yyyy'})
            datetime_format = wb.add_format({'num_format': 'd. mmmm yyyy hh:mm:ss'})
            decimal_format = wb.add_format({'num_format': '0.00'})

            row = 0

            if header:
                for col, head in enumerate(header):
                    ws.write(row, col, force_text(head))
                row += 1

            for data_row in data:
                for col, val in enumerate(data_row):
                    if isinstance(val, datetime):
                        ws.write(row, col, val.replace(tzinfo=None), datetime_format)
                    elif isinstance(val, date):
                        ws.write(row, col, val, date_format)
                    elif isinstance(val, (Decimal, float)):
                        ws.write(row, col, val, decimal_format)
                    elif isinstance(val, str):
                        val = self._prepare_value(val)
                        ws.write(row, col, val)
                    else:
                        ws.write(row, col, val)
                row += 1
            wb.close()

if pisa:
    class PDFGenerator:

        encoding = 'utf-8'

        def generate(self, header, data, output_stream):
            def fetch_resources(uri, rel):
                urls = {
                    django_settings.MEDIA_ROOT: settings.MEDIA_URL,
                    django_settings.STATICFILES_ROOT: django_settings.STATIC_URL
                }
                for k, v in urls.items():
                    if (uri.startswith(v)):
                        return os.path.join(k, uri.replace(v, ""))
                return ''
            pisa.pisaDocument(
                force_text(
                    get_template(settings.PDF_EXPORT_TEMPLATE).render(
                        {'pagesize': 'A4', 'headers': header, 'data': data}
                    )
                ),
                output_stream, encoding=self.encoding, link_callback=fetch_resources
            )
