#!/usr/bin/env sh
set -e

# Add 'celery' to the front of the command if it's not there already
[ "$1" = 'celery' ] || set -- celery "$@"

# Set some common options if the env vars are set
set -- "$@" \
    ${CELERY_APP:+--app "$CELERY_APP"} \
    ${CELERY_BROKER:+--broker "$CELERY_BROKER"} \
    ${CELERY_LOGLEVEL:+--loglevel "$CELERY_LOGLEVEL"}

# Set the concurrency if this is a worker
if [ "$2" = 'worker' ]; then
  set -- "$@" --concurrency "${CELERY_CONCURRENCY:-1}"
fi

# Set the schedule file if this is beat
if [ "$2" = 'beat' ]; then
  set -- "$@" --schedule /var/run/celery/celerybeat-schedule
fi

exec su-exec celery "$@"
