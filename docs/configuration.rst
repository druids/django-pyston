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
