#!/usr/bin/env python
# -*- coding: utf-8 -*-
from piston.version import get_version

try:
    from setuptools import setup, find_packages
except ImportError:
    import ez_setup
    ez_setup.use_setuptools()
    from setuptools import setup, find_packages

setup(
    name="django-piston",
    version=get_version(),
    url='http://bitbucket.org/jespern/django-piston/wiki/Home',
	download_url='http://bitbucket.org/jespern/django-piston/downloads/',
    license='BSD',
    description="Piston is a Django mini-framework creating APIs.",
    author='Jesper Noehr',
    author_email='jesper@noehr.org',
    packages=find_packages(),
    namespace_packages=['piston'],
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP',
    ]
)
