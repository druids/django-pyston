.. _configuration:


Configuration
=============

After installation you must go thought these steps to use django-pyston:

Required Settings
-----------------

The following variables have to be added to or edited in the project's ``settings.py``:

``INSTALLED_APPS``
^^^^^^^^^^^^^^^^^^

For using pyston you just add add ``pyston`` to ``INSTALLED_APPS`` variable::

    INSTALLED_APPS = (
        ...
        'pyston',
        ...
    )


Settings
--------

.. attribute:: PYSTON_CONVERTERS

  List of the allowed pyston converters. Example::

    PYSTON_CONVERTERS = (
        'pyston.converters.JsonConverter',
        'pyston.converters.XmlConverter',
        'pyston.converters.CsvConverter',
        'pyston.converters.XlsxConverter', # only if xlsxwriter library is installed
        'pyston.converters.PdfConverter', # only if xhtml2pdf library is installed
    )


.. attribute:: PYSTON_IGNORE_DUPE_MODELS

  The pyston library checks if one django model has only the one registered resource. You can turn off this check with value ``False``.

.. attribute:: PYSTON_CORS

  Settings set if cors is allowed in the resources. Default value is ``False``. Is recommended to use ``django-cors-headers`` library (https://github.com/adamchainz/django-cors-headers).

.. attribute:: PYSTON_CORS_WHITELIST

  List of whitelisted domains for the cors.

.. attribute:: PYSTON_CORS_MAX_AGE

  The value of the ``Access-Control-Max-Age`` header in seconds. The default value is 30 minutes.

.. attribute:: PYSTON_CORS_MAX_AGE

  The value of the ``Access-Control-Allow-Credentials`` header. The default value is ``True``.

.. attribute:: PYSTON_CORS_ALLOWED_HEADERS

  The value of the ``Access-Control-Allow-Headers`` header. The default value is ``('X-Base', 'X-Offset', 'X-Fields', 'Origin', 'Content-Type', 'Accept')``.

.. attribute:: PYSTON_CORS_ALLOWED_EXPOSED_HEADERS

  The value of the ``Access-Control-Expose-Headers`` header. The default value is ``('X-Total', 'X-Serialization-Format-Options', 'X-Fields-Options')``.

.. attribute:: PYSTON_JSON_CONVERTER_OPTIONS

  Options of the pyston ``pyston.converters.JsonConverter`` which use the json.dumps function. The default value is ``{'indent': 4}``

.. attribute:: PYSTON_PDF_EXPORT_TEMPLATE

  Path to the pdf export html template for ``pyston.converters.PdfConverter``. The default value is ``'default_pdf_table.html'``.

.. attribute:: PYSTON_FILE_SIZE_LIMIT

  Maximum size of the files in bytes which pyston resource accepts. The default value is ``5000000``.

.. attribute:: PYSTON_AUTO_RELATED_REVERSE_FIELDS

  Settings defines if its allowed to create in one REST request the object instance with its reverse related object (if the reverse related object resource is defined too). The default value is ``True``.

.. attribute:: PYSTON_AUTO_RELATED_DIRECT_FIELDS

  Settings defines if its allowed to create in one REST request the object instance with its related object (if the related object resource is defined too). The default value is ``True``.

.. attribute:: PYSTON_PARTIAL_PUT_UPDATE

  The setting sets if the HTTP PUT method has the same behaviour as PATCH. The default value is ``False``.

.. attribute:: PYSTON_PARTIAL_RELATED_UPDATE

  The setting sets if the related objects can be edited partially with the HTTP PUT request. The default value is ``False``.

.. attribute:: PYSTON_ERRORS_RESPONSE_CLASS

  The path to the pyston class generator of error responses with a multiple error messages. The default value is ``'pyston.response.RestErrorsResponse'``.

.. attribute:: PYSTON_ERROR_RESPONSE_CLASS

  The path to the pyston class generator of error responses with a single error messages. The default value is ``'pyston.response.RestErrorResponse'``.

.. attribute:: PYSTON_AUTO_REGISTER_RESOURCE

  Auto register pyston resource for the automatic resource related objects connection. The default value is ``True``.

.. attribute:: PYSTON_ALLOW_TAGS

  The settings value ``False`` defines that the HTML tags should be escaped in the response body. The default value is ``False``.

.. attribute:: PYSTON_DEFAULT_FILENAMES

  Filenames which will be used according to file type if client will not send it. The default value is::

    DEFAULT_FILENAMES = (
        (('pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv'), 'document'),  # for pdf, doc, docx, ... is used document
        (('jpg', 'jpeg', 'png', 'gif', 'tiff', 'bmp', 'svg'), 'image'), # for jpg, jpeg, ... is used image
    )

.. attribute:: PYSTON_DEFAULT_FILENAME

  Filename which will be used according if the file type does not exists in the ``PYSTON_DEFAULT_FILENAMES`` setting. The default value is ``'attachment'``.

.. attribute:: PYSTON_NONE_HUMANIZED_VALUE

  If clients accepts humanized response the None value is converted into this value. The default value is ``'--'``.
