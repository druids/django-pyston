from __future__ import unicode_literals

import csv
import cStringIO
import codecs

from django.utils.encoding import force_text


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
        self.stream.write(b'\ufeff')  # BOM for Excel
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
