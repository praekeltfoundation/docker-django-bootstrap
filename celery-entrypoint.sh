#!/usr/bin/env sh
set -e

_is_celery_command () {
  local cmd="$1"; shift

  python - <<EOF
import sys
from celery.bin.celery import CeleryCommand
sys.exit(0 if '$cmd' in CeleryCommand.commands else 1)
EOF
}

if [ "$1" != 'celery' ]; then
  # If first argument looks like an option or a Celery command, add the 'celery'
  if [ "${1#-}" != "$1" ] || _is_celery_command "$1"; then
    set -- celery "$@"
  fi
fi

if [ "$1" = 'celery' ]; then
  # Set some common options if the env vars are set
  if [ -n "$CELERY_BROKER" ]; then
    echo 'DEPRECATED: The CELERY_BROKER environment variable is deprecated.
            Please set the Celery broker in your Django settings file rather.' 1>&2
    set -- "$@" --broker "$CELERY_BROKER"
  fi

  if [ -n "$CELERY_LOGLEVEL" ]; then
    echo 'DEPRECATED: The CELERY_LOGLEVEL environment variable is deprecated.
            Please set the Celery log level in your Django settings file rather.' 1>&2
    set -- "$@" --loglevel "$CELERY_LOGLEVEL"
  fi

  # Set the concurrency if this is a worker
  if [ "$2" = 'worker' ]; then
    if [ -n "$CELERY_CONCURRENCY" ]; then
      echo 'DEPRECATED: The CELERY_CONCURRENCY environment variable is deprecated.
            Please set the Celery worker concurrency in your Django settings file rather.' 1>&2
    fi
    set -- "$@" --concurrency "${CELERY_CONCURRENCY:-1}"
  fi

  # Run under the celery user
  set -- su-exec django "$@"

  # Celery by default writes files like pidfiles and the beat schedule file to
  # the current working directory. Change to the Celery working directory so
  # that these files end up there.
  cd /var/run/celery
fi

exec "$@"
