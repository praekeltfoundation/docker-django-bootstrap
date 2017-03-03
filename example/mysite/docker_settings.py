from __future__ import absolute_import

import environ

from .settings import *  # noqa

env = environ.Env()

SECRET_KEY = env('SECRET_KEY', SECRET_KEY)  # noqa: F405
DEBUG = env('DEBUG', default=False)
ALLOWED_HOSTS = env('ALLOWED_HOSTS', default=['*'])

DATABASES = {
    'default': env.db(default='sqlite:///db.sqlite3')
}

STATIC_ROOT = '/app/static'
STATIC_URL = '/static/'
STATICFILES_STORAGE = (
    'django.contrib.staticfiles.storage.CachedStaticFilesStorage')

MEDIA_ROOT = '/app/media'
MEDIA_URL = '/media/'

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
            'level': env('DJANGO_LOG_LEVEL', default='INFO'),
        },
        'celery': {
            'handlers': ['console'],
            'level': env('CELERY_LOG_LEVEL', default='INFO'),
        },
    },
}


CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='amqp://')
CELERY_WORKER_CONCURRENCY = env('CELERY_WORKER_CONCURRENCY', default=1)

# Celery 3.1 compatibility
BROKER_URL = CELERY_BROKER_URL
CELERYD_CONCURRENCY = CELERY_WORKER_CONCURRENCY
