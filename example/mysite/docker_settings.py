from __future__ import absolute_import

import environ

from .settings import *  # noqa

env = environ.Env()

SECRET_KEY = env('SECRET_KEY')

DATABASES = {
    'default': env.db(default='sqlite:///db.sqlite3')
}

STATIC_ROOT = '/app/static'
STATIC_URL = '/static/'

MEDIA_ROOT = '/app/media'
MEDIA_URL = '/media/'

CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='amqp://')
CELERY_LOG_LEVEL = env('CELERY_LOG_LEVEL', default='INFO')
CELERY_WORKER_CONCURRENCY = env('CELERY_WORKER_CONCURRENCY', default=1)

# Celery 3.1 compatibility
BROKER_URL = CELERY_BROKER_URL
CELERYD_CONCURRENCY = CELERY_WORKER_CONCURRENCY
