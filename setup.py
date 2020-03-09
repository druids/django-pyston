from setuptools import setup, find_packages

from pyston.version import get_version


setup(
    name="django-pyston",
    version=get_version(),
    description="Pyston is a Django mini-framework creating APIs.",
    author='Lubos Matl',
    author_email='matllubos@gmail.com',
    url='https://github.com/matllubos/django-pyston',
    license='BSD',
    package_dir={'pyston': 'pyston'},
    include_package_data=True,
    packages=find_packages(),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP',
    ],
    install_requires=[
        'django>=1.11',
        'python-mimeparse>=1.6.0',
        'django-chamber>=0.5.6',
        'pyparsing>=2.4.2',
        'defusedxml>=0.6.0',
    ],
    zip_safe=False
)
