.. _exceptions:

=================
Pyston exceptions
=================

Pyston raises some of its own exceptions as well as standard Python exceptions.

Pyston Core Exceptions
======================

.. module:: pyston.exception
    :synopsis: Pyston core exceptions

Pyston core exception classes are defined in ``pyston.exception``.

``UnsupportedMediaTypeException``
---------------------------------

.. exception:: UnsupportedMediaTypeException

    Exception raises resource if requested content type is not supported.

``MimerDataException``
----------------------

.. exception:: MimerDataException

    Exception raises resource if content type cannot be evaluated.

``RESTException``
-----------------

.. exception:: RESTException

    Base rest exception that contains string message.

``ResourceNotFoundException``
-----------------------------

.. exception:: ResourceNotFoundException

    Exception that is raised if object of resource was not found.


``NotAllowedException``
-----------------------

.. exception:: NotAllowedException

    Operation is not allowed for logged user.

``NotAllowedMethodException``
-----------------------------

.. exception:: NotAllowedMethodException

    Resource doesn't allow use concrete HTTP method.

``DuplicateEntryException``
---------------------------

.. exception:: DuplicateEntryException

    Exception is raised if there is some duplicite (e.q. newly created object already exists)

``ConflictException``
---------------------

.. exception:: ConflictException

    Exception is raised if object already exists but user isn't allowed to change it.

``DataInvalidException``
------------------------

.. exception:: DataInvalidException

    This exception contains Forms exceptions. It is errors invoked by request structure or form validations.

Pyston Form Exceptions
======================

.. module:: pyston.forms
    :synopsis: Pyston form exceptions

Pyston forms exception classes are defined in ``pyston.forms``.

``RESTError``
-------------

.. exception:: RESTError

    This is base exception for all form errors.

``RESTListError``
-----------------

.. exception:: RESTListError

    Exception that contains list of another ``RESTError`` classes. Exception simulates python list object and provides
    all of lists methods but can be raised like exception.

``RESTDictError``
-----------------

.. exception:: RESTDictError

    Exception that contains dict of another ``RESTError`` classes. Exception simulates python dict object and provides
    all of lists methods but can be raised like exception.

``RESTDictIndexError``
----------------------

.. exception:: RESTDictIndexError

    ``RESTDictIndexError`` is often used inside ``RESTListError``. It contains idex of element where error was happend
    and data in ``RESTDictError`` format.

``RESTValidationError``
-----------------------

.. exception:: RESTValidationError

    ``RESTValidationError`` is similar to django ``ValidationError`` but it can contain only one error message with one
    code.
