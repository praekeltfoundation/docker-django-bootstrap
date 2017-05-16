from setuptools import setup, find_packages

setup(
    name='mysite',
    version='0.1',
    author='Praekelt.org',
    author_email='sre@praekelt.org',
    packages=find_packages(),
    install_requires=[
        'celery >=4.0, <4.1',
        'Django >=1.11, <1.12',
        'django-environ',
        'psycopg2 >=2.7',
    ],
)
