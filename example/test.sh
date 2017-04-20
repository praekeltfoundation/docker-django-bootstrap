#!/usr/bin/env bash
set -e

function usage() {
  echo "usage: $1 [-s|--single-image]"
}

EXTRA_COMPOSE_FILE=
WORKER_SERVICE=worker
BEAT_SERVICE=beat
# 1. dinit
# 2. gunicorn master
# 3. gunicorn worker
# 4. nginx master
# 5. nginx worker
EXPECTED_WEB_PROCESSES=5
case "$1" in
  -s|--single-container)
    EXTRA_COMPOSE_FILE=docker-compose.single-container.yml
    WORKER_SERVICE=web
    BEAT_SERVICE=web
    # 6. celery worker
    # 7. celery beat
    EXPECTED_WEB_PROCESSES=7
  ;;
  '') ;;
  *)
    usage "$0" >&2; exit 1
  ;;
esac

# macOS-compatible timeout function: http://stackoverflow.com/a/35512328
function timeout() { perl -e 'alarm shift; exec @ARGV' "$@"; }

function wait_for_log_line() {
  local service="$1"; shift
  local log_pattern="$1"; shift
  timeout "${LOG_TIMEOUT:-10}" grep -m 1 -E "$log_pattern" <(compose_cmd logs -f "$service" 2>&1)
}

function compose_cmd() {
  docker-compose -f docker-compose.yml ${EXTRA_COMPOSE_FILE:+-f "$EXTRA_COMPOSE_FILE"} "$@"
}

# Set a trap on errors to make it clear when tests have failed
trap '{ set +x; echo; echo FAILED; echo; } >&2' ERR

# Set a trap to bring everything down when we exit
trap "{ set +x; compose_cmd down; }" EXIT

set -x

# Bring up the DB and AMQP first
compose_cmd up -d db amqp
wait_for_log_line db 'database system is ready to accept connections'
wait_for_log_line amqp 'Server startup complete'

# Bring up the web
compose_cmd up -d web

# Django tests
# ############
wait_for_log_line web 'Booting worker'
compose_cmd ps web | grep 'Up'

WEB_PORT="$(compose_cmd port web 8000 | cut -d':' -f2)"

# Simple check to see if the site is up
curl -fsL http://localhost:$WEB_PORT/admin | fgrep '<title>Log in | Django site admin</title>'

# Check that we can get a static file served by Nginx
curl -fsL http://localhost:$WEB_PORT/static/admin/css/base.css | fgrep 'DJANGO Admin styles'

# Check that the caching header is set for a hashed file
curl -fsI http://localhost:$WEB_PORT/static/admin/img/search.7cf54ff789c6.svg | fgrep 'Cache-Control: max-age=315360000'

# Check that the caching header is *not* set for a file that isn't hashed
curl -fsI http://localhost:$WEB_PORT/static/admin/img/search.svg | fgrep -v 'Cache-Control'

# Check tables were created in the database
[[ $(compose_cmd exec --user postgres db \
  psql -q --dbname mysite -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" \
    | grep -E '^\s*[[:digit:]]+' | tr -d ' ') > 0 ]]


# Celery tests
# ############
# Assert the expected number of processes are running in the web container
[ "$(compose_cmd exec web ps ax --no-headers | grep -v 'ps ax' | wc -l | tr -d ' ')" \
  = "$EXPECTED_WEB_PROCESSES" ]

# Celery worker
[ "$WORKER_SERVICE" = 'web' ] || docker-compose up -d "$WORKER_SERVICE"
wait_for_log_line "$WORKER_SERVICE" 'celery@\w+ ready'
[ "$WORKER_SERVICE" = 'web' ] || compose_cmd ps "$WORKER_SERVICE" | grep 'Up'

# Celery beat
[ "$BEAT_SERVICE" = 'web' ] || docker-compose up -d "$BEAT_SERVICE"
wait_for_log_line "$BEAT_SERVICE" 'beat: Starting\.\.\.'
[ "$BEAT_SERVICE" = 'web' ] || compose_cmd ps "$BEAT_SERVICE" | grep 'Up'

# Check a queue was created in RabbitMQ
compose_cmd exec amqp rabbitmqctl list_queues -p /mysite | grep 'celery'

set +x
echo
echo "PASSED"
