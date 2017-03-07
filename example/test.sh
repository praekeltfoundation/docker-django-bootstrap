#!/usr/bin/env bash
set -e

# Set a trap on errors to make it clear when tests have failed
trap '{ set +x; echo; echo FAILED; echo; } >&2' ERR

# Set a trap to bring everything down when we exit
trap "{ set +x; docker-compose down; }" EXIT

# macOS-compatible timeout function: http://stackoverflow.com/a/35512328
function timeout() { perl -e 'alarm shift; exec @ARGV' "$@"; }

function wait_for_log_line() {
  local service="$1"; shift
  local log_pattern="$1"; shift
  timeout "${LOG_TIMEOUT:-10}" grep -m 1 -E "$log_pattern" <(docker-compose logs -f "$service" 2>&1)
}

set -x

# Bring up the DB and AMQP first
docker-compose up -d db amqp
wait_for_log_line db 'database system is ready to accept connections'
wait_for_log_line amqp 'Server startup complete'

# Bring everything else up
docker-compose up -d

# Django tests
# ############
wait_for_log_line web 'Booting worker'
docker-compose ps web | grep 'Up'

WEB_PORT="$(docker-compose port web 8000 | cut -d':' -f2)"

# Simple check to see if the site is up
curl -fsL http://localhost:$WEB_PORT/admin | fgrep '<title>Log in | Django site admin</title>'

# Check that we can get a static file served by Nginx
curl -fsL http://localhost:$WEB_PORT/static/admin/css/base.css | fgrep 'DJANGO Admin styles'

# Check that the caching header is set for a hashed file
curl -fsI http://localhost:$WEB_PORT/static/admin/img/search.7cf54ff789c6.svg | fgrep 'Cache-Control: max-age=315360000'

# Check that the caching header is *not* set for a file that isn't hashed
curl -fsI http://localhost:$WEB_PORT/static/admin/img/search.svg | fgrep -v 'Cache-Control'

# Check tables were created in the database
[[ $(docker-compose exec --user postgres db \
  psql -q --dbname mysite -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" \
    | grep -E '^\s*[[:digit:]]+' | tr -d ' ') > 0 ]]


# Celery tests
# ############
# Check the logs to see if the Celery worker started up successfully
wait_for_log_line worker 'celery@\w+ ready'
docker-compose ps worker | grep 'Up'

# Check the logs to see if Celery beat started up successfully
wait_for_log_line beat 'beat: Starting\.\.\.'
docker-compose ps beat | grep 'Up'

# Check a queue was created in RabbitMQ
docker-compose exec amqp rabbitmqctl list_queues -p /mysite | grep 'celery'

set +x
echo
echo "PASSED"
