from setuptools import setup

setup(
    name='mysite',
    version='0.1',
    author='Praekelt.org',
    author_email='sre@praekelt.org',
    packages=['mysite'],
    install_requires=[
        'celery >=5.2.2, <6',
        'Django >=2.2.2, <2.3',
        'django_compressor >=2.1',
        'django-environ',
        'django-health-check',
        'django-prometheus <2.3',
        'psycopg2-binary >=2.7',
    ],
)
