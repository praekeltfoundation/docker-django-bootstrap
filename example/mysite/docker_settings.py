# An example settings file for deploying a Django app in a Docker container.
# Uses environment variables to configure the majority of settings. This
# pattern is sometimes attributed to the '12factor' app guidelines:
# https://12factor.net/config

from __future__ import absolute_import

# We use django-environ here to make working with environment variables a bit
# easier: https://github.com/joke2k/django-environ. To use this, you'll need to
# add 'django-environ' to your install_requires.
import environ

# Import the existing settings file, we'll work from there...
from .settings import ALLOWED_HOSTS, SECRET_KEY
from .settings import *  # noqa

env = environ.Env()

SECRET_KEY = env.str('SECRET_KEY', default=SECRET_KEY)
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=ALLOWED_HOSTS)

DATABASES = {
    # django-environ builds in the functionality of dj-database-url
    # (https://github.com/kennethreitz/dj-database-url). This allows you to
    # fully configure the database connection using a single environment
    # variable that defines a 'database URL', for example:
    # `DATABASE_URL=postgres://username:password@db-host/db-name`
    'default': env.db(default='sqlite:///db.sqlite3')
}

# Set up static file storage as described in the README
STATIC_ROOT = '/app/static'
STATIC_URL = '/static/'
# Using CachedStaticFilesStorage results in a larger Docker image but means
# that Nginx can set long 'expires' headers for the files.
# https://github.com/praekeltfoundation/docker-django-bootstrap/pull/11
STATICFILES_STORAGE = (
    'django.contrib.staticfiles.storage.CachedStaticFilesStorage')

MEDIA_ROOT = '/app/media'
MEDIA_URL = '/media/'

# Logs are dealt with a bit differently in Docker-land. We don't really want to
# log to files as Docker containers should be ephemeral and so the files may
# be lost as soon as the container stops. Instead, we want to log to
# stdout/stderr and have those streams handled by the Docker daemon.
# https://docs.djangoproject.com/en/1.10/topics/logging/#configuring-logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(name)s %(levelname)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': env.str('DJANGO_LOG_LEVEL', default='INFO'),
        },
        'celery': {
            'handlers': ['console'],
            'level': env.str('CELERY_LOG_LEVEL', default='INFO'),
        },
    },
}

# Configure Celery using environment variables. These require that there is a
# `celery.py` file in the project that tells Celery to read config from your
# Django settings:
# http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html
CELERY_BROKER_URL = env.str('CELERY_BROKER_URL', default='amqp://')
# *** This line is important! We want the worker concurrency to default to 1.
# If we don't do this it will default to the number of CPUs on the particular
# machine that we run the container on, which means unpredictable resource
# usage on a cluster of mixed hosts.
CELERY_WORKER_CONCURRENCY = env.int('CELERY_WORKER_CONCURRENCY', default=1)

# Celery 3.1 compatibility
BROKER_URL = CELERY_BROKER_URL
CELERYD_CONCURRENCY = CELERY_WORKER_CONCURRENCY
