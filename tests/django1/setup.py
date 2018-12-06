import sys

from setuptools import setup


install_requires = [
    'celery >=4.2, <4.3',
    'Django >=1.11, <1.12',
    'django_compressor >=2.1',
    'django-environ',
    'psycopg2 >=2.7',
]
if sys.version_info[0] < 3:
    install_requires.append('django-health-check <3')
else:
    install_requires.append('django-health-check')

setup(
    name='mysite',
    version='0.1',
    author='Praekelt.org',
    author_email='sre@praekelt.org',
    packages=['mysite'],
    install_requires=install_requires,
)
