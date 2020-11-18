import sys

from setuptools import setup


install_requires = [
    'celery >=4.2, <4.3',
    'Django >=1.11, <1.12',
    'django-appconf <1.0.3',  # Last version with py27 support.
    'django_compressor >=2.1, <2.4',  # Last version with py27 support.
    'django-environ',
    'django-prometheus <2',
    'psycopg2 >=2.7',
    'django-health-check <3',
]

setup(
    name='mysite',
    version='0.1',
    author='Praekelt.org',
    author_email='sre@praekelt.org',
    packages=['mysite'],
    install_requires=install_requires,
)
