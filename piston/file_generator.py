from __future__ import unicode_literals

import os
import csv
import cStringIO
import codecs

from datetime import datetime, date
from decimal import Decimal

from django.template import Context
from django.template.loader import get_template
from django.utils.encoding import force_text
from django.conf import settings

try:
    # xlsxwriter isn't standard with python.  It shouldn't be required if it
    # isn't used.
    import xlsxwriter
except ImportError:
    xlsxwriter = None
    XlsxGenerator = None


try:
    # pisa isn't standard with python. It shouldn't be required if it isn't used.
    from xhtml2pdf import pisa
except ImportError:
    pisa = None
    PdfGenerator = None


TWOPLACES = Decimal(10) ** -2


class CsvGenerator(object):

    def __init__(self, delimiter=b';', quotechar=b'"', encoding='utf-8'):
        self.encoding = encoding
        self.quotechar = quotechar
        self.delimiter = delimiter

    def generate(self, header, data, output_stream):
        writer = UnicodeWriter(output_stream, delimiter=self.delimiter, quotechar=self.quotechar, quoting=csv.QUOTE_ALL)

        if header:
            writer.writerow(self._prepare_list(header))

        for row in data:
            writer.writerow(self._prepare_list(row))

    def _prepare_list(self, values):
        prepared_row = []

        for value in values:
            value = self._prepare_value(value.get('value') if isinstance(value, dict) else value);
            prepared_row.append(value)
        return prepared_row

    def _prepare_value(self, value):
        if isinstance(value, float):
            value = ('%.2f' % value).replace('.', ',')
        elif isinstance(value, Decimal):
            value = force_text(value.quantize(TWOPLACES)).replace('.', ',')
        else:
            value = force_text(value)
        return value


class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    https://docs.python.org/2/library/csv.html
    """

    def __init__(self, f, dialect=csv.excel, encoding='utf-8', **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.stream.write(codecs.BOM_UTF8)  # BOM for Excel
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode('utf-8') for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        # ... and reencode it into the target encoding
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


if xlsxwriter:
    class XlsxGenerator(object):

        def generate(self, header, data, output_stream):
            wb = xlsxwriter.Workbook(output_stream)
            ws = wb.add_worksheet()

            date_format = wb.add_format({'num_format': 'd. mmmm yyyy'})
            datetime_format = wb.add_format({'num_format': 'd. mmmm yyyy hh:mm:ss'})
            decimal_format = wb.add_format({'num_format': '0.00'})

            row = 0
            if header:
                for col, head in enumerate(header):
                    ws.write(row, col, unicode(head))
                row += 1

            for data_row in data:
                for col, val in enumerate(data_row):
                    if isinstance(val, datetime):
                        ws.write(row, col, val.replace(tzinfo=None), datetime_format)
                    elif isinstance(val, date):
                        ws.write(row, col, val, date_format)
                    elif isinstance(val, (Decimal, float)):
                        ws.write(row, col, val, decimal_format)
                    else:
                        ws.write(row, col, val)
                row += 1

            wb.close()

if pisa:
    class PdfGenerator(object):

        template_name = getattr(settings, 'PDF_EXPORT_TEMPLATE', 'default_pdf_table.html')
        encoding = 'utf-8'

        def generate(self, header, data, output_stream):
            def fetch_resources(uri, rel):
                urls = {settings.MEDIA_ROOT: settings.MEDIA_URL, settings.STATICFILES_ROOT: settings.STATIC_URL}
                for k, v in urls.items():
                    if (uri.startswith(v)):
                        return os.path.join(k, uri.replace(v, ""))
                return ''
            context = Context({'pagesize': 'A4', 'headers': header, 'data': data})
            template = get_template(self.template_name)
            html = template.render(context)

            pisa.pisaDocument(cStringIO.StringIO(html.encode(self.encoding)), output_stream, encoding=self.encoding,
                              link_callback=fetch_resources)
