#!/usr/bin/env sh
set -e

# No args or looks like options or the APP_MODULE for Gunicorn
if [ "$#" = 0 ] || \
    [ "${1#-}" != "$1" ] || \
    echo "$1" | grep -Eq '^([_A-Za-z]\w*\.)*[_A-Za-z]\w*:[_A-Za-z]\w*$'; then
  set -- gunicorn "$@"
fi

# Looks like a Celery command, let's run that with Celery's entrypoint script
if [ "$1" = 'celery' ]; then
  set -- celery-entrypoint.sh "$@"
fi

if [ "$1" = 'gunicorn' ]; then
  # Do a chown of the /app/media & /app/mediafiles directories (if they exist)
  # at runtime in case the directory was mounted as a root-owned volume.
  for media in /app/media /app/mediafiles; do
    if [ -d $media ] && [ "$(stat -c %U $media)" != 'django' ]; then
      chown -R django:django $media
    fi
  done

  # Run the migration as the django user so that if it creates a local DB
  # (e.g. when using sqlite in development), that DB is still writable.
  # Ultimately, the user shouldn't really be using a local DB and it's difficult
  # to offer support for all the cases in which a local DB might be created --
  # but here we do the minimum.
  if [ -z "$SKIP_MIGRATIONS" ]; then
    su-exec django django-admin migrate --noinput
  fi

  if [ -n "$SUPERUSER_PASSWORD" ]; then
    echo "from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', '$SUPERUSER_PASSWORD')
" | su-exec django django-admin shell
    echo "Created superuser with username 'admin' and password '$SUPERUSER_PASSWORD'"
  fi

  nginx -g 'daemon off;' &

  # Celery
  ensure_celery_app() {
    [ -n "$CELERY_APP" ] || \
      { echo 'If $CELERY_WORKER or $CELERY_BEAT are set then $CELERY_APP must be provided'; exit 1; }
  }

  if [ -n "$CELERY_WORKER" ]; then
    ensure_celery_app
    celery-entrypoint.sh worker --pool=solo --pidfile worker.pid &
  fi

  if [ -n "$CELERY_BEAT" ]; then
    ensure_celery_app
    celery-entrypoint.sh beat --pidfile beat.pid &
  fi

  if [ -n "$APP_MODULE" ]; then
    echo 'DEPRECATED: Providing APP_MODULE via an environment variable is deprecated.
            Please provide it using the container command rather.' 1>&2
    set -- "$@" "$APP_MODULE"
  fi

  # Set some sensible Gunicorn options, needed for things to work with Nginx

  # umask working files (worker tmp files & unix socket) as 0o117 (i.e. chmod as
  # 0o660) so that they are only read/writable by django and nginx users.
  set -- su-exec django "$@" \
    --pid /var/run/gunicorn/gunicorn.pid \
    --bind unix:/var/run/gunicorn/gunicorn.sock \
    --umask 0117 \
    ${GUNICORN_ACCESS_LOGS:+--access-logfile -}
fi

exec "$@"
