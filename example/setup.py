from platform import python_implementation
from setuptools import setup, find_packages

install_requires = [
    'celery >=3.1, <4.0',
    'Django >=1.10, <1.11',
    'django-environ',
]
install_requires.append(
    'psycopg2cffi' if python_implementation() == 'PyPy' else 'psycopg2')

setup(
    name='mysite',
    version='0.1',
    author='Praekelt.org',
    author_email='sre@praekelt.org',
    packages=find_packages(),
    install_requires=install_requires,
)
