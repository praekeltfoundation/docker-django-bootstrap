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
  set -- "$@" \
      ${CELERY_APP:+--app "$CELERY_APP"} \
      ${CELERY_BROKER:+--broker "$CELERY_BROKER"} \
      ${CELERY_LOGLEVEL:+--loglevel "$CELERY_LOGLEVEL"}

  # Set the concurrency if this is a worker
  if [ "$2" = 'worker' ]; then
    set -- "$@" --concurrency "${CELERY_CONCURRENCY:-1}"
  fi

  # Run under the celery user
  set -- su-exec celery "$@"

  # Change to the Celery working directory (only place the user can write)
  cd /var/run/celery
fi

exec "$@"
