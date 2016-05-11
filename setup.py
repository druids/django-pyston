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
        'django>=1.6',
        'python-mimeparse>=1.5.1',
        'django-chamber>=0.1.13'
    ],
    dependency_links=[
        'https://github.com/druids/django-chamber/tarball/0.1.13#egg=django-chamber-0.1.13'
    ],
    zip_safe=False
)
