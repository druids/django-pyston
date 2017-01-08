.. _installation:

Installation
============

Requirements
------------

Python/Django versions
^^^^^^^^^^^^^^^^^^^^^^

+-----------------+------------+
|  Python         | Django     |
+=================+============+
| 2.7, 3.4, 3.5   | 1.8 - 1.10 |
+-----------------+------------+


Requirements
^^^^^^^^^^^^

 * **python-mimeparse** - A module provides basic functions for parsing mime-type names and matching them against a list of media-ranges. Pyston uses it to evaluate which response format should be returned.
 * **django-chamber** - Our library of helpers that simplify development (https://github.com/druids/django-chamber)

Libraries are dependecies defined inside setup file.

Using Pip
---------

Django is core is not currently inside *PyPE* but in the future you will be able to use:

.. code-block:: console

    $ pip install django-pyston


Because *django-pston* is rapidly evolving framework the best way how to install it is use source from github

.. code-block:: console

    $ pip install https://github.com/druids/django-pyston/tarball/{{ version }}#egg=django-pyston-{{ version }}

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
