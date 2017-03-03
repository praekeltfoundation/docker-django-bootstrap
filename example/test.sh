#!/usr/bin/env bash
set -e

# Set a trap on errors to make it clear when tests have failed
trap '{ set +x; echo; echo FAILED; echo; } >&2' ERR

set -x

# Bring up the DB and AMQP first
docker-compose up -d db amqp && sleep 5

# Bring everything else up
docker-compose up -d && sleep 5

# Set a trap to bring everything down when we exit
trap "{ set +x; docker-compose down; }" EXIT

# Django tests
# ############
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
docker-compose ps worker | grep 'Up'
docker-compose ps beat | grep 'Up'

# Check the logs to see if the Celery worker started up successfully
docker-compose logs worker | grep -o 'celery@\w\+ ready'

# Check the logs to see if Celery beat started up successfully
docker-compose logs beat | fgrep 'beat: Starting...'

# Check a queue was created in RabbitMQ
docker-compose exec amqp rabbitmqctl list_queues -p /mysite | grep 'celery'

set +x
echo
echo "PASSED"
