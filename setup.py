from setuptools import setup, find_packages

from piston.version import get_version


setup(
    name="django-piston",
    version=get_version(),
    description="Piston is a Django mini-framework creating APIs.",
    author='Lubos Matl',
    author_email='matllubos@gmail.com',
    url='https://github.com/matllubos/django-piston',
    license='BSD',
    package_dir={'piston': 'piston'},
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
        'mimeparse>=0.1.3',
        'django-chamber>=0.0.16'
    ],
    dependency_links=[
        'https://github.com/matllubos/django-chamber/tarball/0.0.16#egg=django-chamber-0.0.16'
    ],
    zip_safe=False
)
