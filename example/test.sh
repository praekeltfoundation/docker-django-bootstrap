#!/usr/bin/env bash
set -e

# Set a trap on errors to make it clear when tests have failed
trap '{ set +x; echo; echo FAILED; echo; } >&2' ERR

function service_ip() {
  local service_name="$1"; shift
  docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$(docker-compose ps -q $service_name)"
}

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

WEB_IP="$(service_ip web)"

# Simple check to see if the site is up
curl -fsL http://$WEB_IP:8000/admin | fgrep '<title>Log in | Django site admin</title>'

# Check that we can get a static file served by Nginx
curl -fsL http://$WEB_IP:8000/static/admin/css/base.css | fgrep 'DJANGO Admin styles'

# Check that the caching header is set for a hashed file
curl -fsI http://$WEB_IP:8000/static/admin/img/search.7cf54ff789c6.svg | fgrep 'Cache-Control: max-age=315360000'

# Check that the caching header is *not* set for a file that isn't hashed
curl -fsI http://$WEB_IP:8000/static/admin/img/search.svg | fgrep -v 'Cache-Control'

# Check tables were created in the database
[[ $(docker-compose exec --user postgres db \
  psql -q --dbname mysite -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" \
    | grep -P '^\s*\d+' | tr -d ' ') > 0 ]]


# Celery tests
# ############
docker-compose ps worker | grep 'Up'
docker-compose ps beat | grep 'Up'

# Check the logs to see if the Celery worker started up successfully
docker-compose logs worker 2>&1 | fgrep 'celery@mysite-celery ready'

# Check the logs to see if Celery beat started up successfully
docker-compose logs beat 2>&1 | fgrep 'beat: Starting...'

set +x
echo
echo "PASSED"
