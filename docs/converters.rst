.. _converters:

Converters
==========

Pyston converters are used to serialize/deserialize response/request data to the required format. Converters are selected according to ``Content-type`` and ``Accept`` HTTP header.

Deserialization
---------------

Data is automatically deserialized from HTTP request body to the python format (basic python data types: string, boolean, integer, dict, list, etc.)

If converter is used for deserialization (is not required) it must implement this method::

    def _decode(self, data, **kwargs):
        """
        Should return deserialized data in the python format
        """


Serialization
-------------

Serialized data prepared with serializers are automatically serialized to the output stream. Output stream doesn't be only response but it can be ByteIO too to serialize data directly to the string.

Converter must implement one of these methods::

    def _encode(self, data, options=None, **kwargs):
        """
        Should return serialized data in the string format
        """

or::

    def _encode_to_stream(self, os, data, options=None, **kwargs):
        """
        Should contains implementation that writes data to the output stream (os)
        """

As example of full converter (with serialization and deserialization) we can use ``JSONConverter``::

    class JSONConverter(Converter):
        """
        JSON emitter, understands timestamps.
        """
        media_type = 'application/json'
        format = 'json'

        def _encode_to_stream(self, os, data, options=None, **kwargs):
            options = settings.JSON_CONVERTER_OPTIONS if options is None else options
            if data:
                json.dump(data, os, cls=LazyDateTimeAwareJSONEncoder, ensure_ascii=False, **options)

        def _decode(self, data, **kwargs):
            return json.loads(data)

Configuration
-------------

Converters can be configured inside django settings file with attribute ``PYSTON_CONVERTERS``. ``PYSTON_CONVERTERS`` default content is::

    PYSTON_CONVERTERS = (
        'pyston.converters.JSONConverter',
        'pyston.converters.XMLConverter',
        'pyston.converters.CSVConverter',
        'pyston.converters.XLSXConverter', # only if xlsxwriter library is installed
        'pyston.converters.PDFConverter', # only if xhtml2pdf library is installed
    )

Converters can be changed in concrete REST resource class with parameter ``converter_classes``. There can be converter defined as a path to the converter in the string format or as an class.

All converters is defined inside following list with its description:

 * ``pyston.converters.JSONConverter`` - full converter that serialize/deserialize data to/from JSON format.
 * ``pyston.converters.XMLConverter`` - only deserialize data to XML format.
 * ``pyston.converters.CSVConverter`` - only deserialize data to CSV format.
 * ``pyston.converters.XLSXConverter`` - only deserialize data to XLSX format. You must firstly install library xlsxwriter to use this converter.
 * ``pyston.converters.PDFConverter`` - only deserialize data to PDF format. You must firstly install library xhtml2pdf to use this converter.
 * ``pyston.converters.HTMLConverter`` - only deserialize data to HTML format. This converter should be used only for dev purpose and shouldn't be deployes on production environment.