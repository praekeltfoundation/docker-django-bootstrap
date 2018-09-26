from setuptools import setup

setup(
    name='mysite',
    version='0.1',
    author='Praekelt.org',
    author_email='sre@praekelt.org',
    packages=['mysite'],
    install_requires=[
        'celery >=4.2, <4.3',
        'Django >=2.1, <2.2',
        'django_compressor >=2.1',
        'django-environ',
        'psycopg2 >=2.7',
    ],
)
