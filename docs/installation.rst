.. _installation:

Installation
============

Requirements
------------

Python/Django versions
^^^^^^^^^^^^^^^^^^^^^^

+----------------------------+------------------+
|  Python                    | Django           |
+============================+==================+
| 3.5, 3.6, 3.9, 3.10, 3.11  | >=2.2 <4         |
+----------------------------+------------------+


Requirements
^^^^^^^^^^^^

 * **python-mimeparse** - A module provides basic functions for parsing mime-type names and matching them against a list of media-ranges. Pyston uses it to evaluate which response format should be returned.
 * **django-chamber** - Our library of helpers that simplify development (https://github.com/druids/django-chamber)
 * **pyparsing** - to parse the filter logical expressions
 * **defusedxml** - to parse XML data to the response body with the ``XmlConverter``

Libraries dependencies are defined inside the setup file.

Using Pip
---------

Django pyston is not currently inside *PyPE* but in the future you will be able to use:

.. code-block:: console

    $ pip install django-pyston


Because *django-pston* is rapidly evolving framework the best way how to install it is use source from github

.. code-block:: console

    $ pip install https://github.com/druids/django-pyston/tarball/{{ version }}#egg=django-pyston-{{ version }}
