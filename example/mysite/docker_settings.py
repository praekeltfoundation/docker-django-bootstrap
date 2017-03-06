from __future__ import absolute_import

import environ

try:
    from psycopg2cffi import compat
    compat.register()
except ImportError:
    pass

from .settings import ALLOWED_HOSTS, SECRET_KEY
from .settings import *  # noqa

env = environ.Env()

SECRET_KEY = env.str('SECRET_KEY', default=SECRET_KEY)
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=ALLOWED_HOSTS)

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
            'level': env.str('DJANGO_LOG_LEVEL', default='INFO'),
        },
        'celery': {
            'handlers': ['console'],
            'level': env.str('CELERY_LOG_LEVEL', default='INFO'),
        },
    },
}


CELERY_BROKER_URL = env.str('CELERY_BROKER_URL', default='amqp://')
CELERY_WORKER_CONCURRENCY = env.int('CELERY_WORKER_CONCURRENCY', default=1)

# Celery 3.1 compatibility
BROKER_URL = CELERY_BROKER_URL
CELERYD_CONCURRENCY = CELERY_WORKER_CONCURRENCY
