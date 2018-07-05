from setuptools import setup

setup(
    name='mysite',
    version='0.1',
    author='Praekelt.org',
    author_email='sre@praekelt.org',
    packages=['mysite'],
    install_requires=[
        'celery >=4.2, <4.3',
        # This version seems to be broken with Python 3:
        # https://github.com/celery/py-amqp/issues/155
        'amqp != 2.2.0',
        'Django >=1.11, <1.12',
        'django_compressor >=2.1',
        'django-environ',
        'psycopg2 >=2.7',
    ],
)
