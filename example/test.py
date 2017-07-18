#!/usr/bin/env python3
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import iso8601
import pytest
import requests
from testtools.assertions import assert_that
from testtools.matchers import (
    AfterPreprocessing as After, Contains, Equals, GreaterThan, HasLength,
    LessThan, MatchesAll, MatchesAny, MatchesDict, MatchesListwise,
    MatchesRegex, MatchesSetwise, Not)

from docker_helper import (
    DockerHelper, list_container_processes, output_lines, wait_for_log_line)


# Turn off spam from all the random loggers that set themselves up behind us.
for logger in logging.Logger.manager.loggerDict.values():
    if isinstance(logger, logging.Logger):
        logger.setLevel(logging.WARNING)
# Turn on spam from the loggers we're interested in.
logging.getLogger('docker_helper.helper').setLevel(logging.DEBUG)

POSTGRES_IMAGE = 'postgres:9.6-alpine'
POSTGRES_PARAMS = {
    'service': 'db',
    'db': 'mysite',
    'user': 'mysite',
    'password': 'secret',
}
RABBITMQ_IMAGE = 'rabbitmq:3.6-alpine'
RABBITMQ_PARAMS = {
    'service': 'amqp',
    'vhost': '/mysite',
    'user': 'mysite',
    'password': 'secret',
}
DATABASE_URL = (
    'postgres://{user}:{password}@{service}/{db}'.format(**POSTGRES_PARAMS))
BROKER_URL = (
    'amqp://{user}:{password}@{service}/{vhost}'.format(**RABBITMQ_PARAMS))


@pytest.fixture(scope='module')
def docker_helper():
    docker_helper = DockerHelper()
    docker_helper.setup()
    yield docker_helper
    docker_helper.teardown()


@pytest.fixture(scope='module')
def raw_db_container(docker_helper):
    docker_helper.pull_image_if_not_found(POSTGRES_IMAGE)

    container = docker_helper.create_container(
        POSTGRES_PARAMS['service'], POSTGRES_IMAGE, environment={
            'POSTGRES_USER': POSTGRES_PARAMS['user'],
            'POSTGRES_PASSWORD': POSTGRES_PARAMS['password'],
        },
        tmpfs={'/var/lib/postgresql/data': 'uid=70,gid=70'})
    docker_helper.start_container(container)
    wait_for_log_line(
        container, r'database system is ready to accept connections')
    yield container
    docker_helper.stop_and_remove_container(container)


def clean_db(db_container):
    db = POSTGRES_PARAMS['db']
    user = POSTGRES_PARAMS['user']
    db_container.exec_run(['dropdb', db], user='postgres')
    db_container.exec_run(['createdb', '-O', user, db], user='postgres')


@pytest.fixture
def db_container(request, raw_db_container):
    if 'clean_db' in request.keywords:
        clean_db(raw_db_container)
    return raw_db_container


@pytest.fixture(scope='module')
def raw_amqp_container(docker_helper):
    docker_helper.pull_image_if_not_found(RABBITMQ_IMAGE)

    container = docker_helper.create_container(
        RABBITMQ_PARAMS['service'], RABBITMQ_IMAGE, environment={
            'RABBITMQ_DEFAULT_USER': RABBITMQ_PARAMS['user'],
            'RABBITMQ_DEFAULT_PASS': RABBITMQ_PARAMS['password'],
            'RABBITMQ_DEFAULT_VHOST': RABBITMQ_PARAMS['vhost'],
        },
        tmpfs={'/var/lib/rabbitmq': 'uid=100,gid=101'})
    docker_helper.start_container(container)
    wait_for_log_line(container, r'Server startup complete')
    yield container
    docker_helper.stop_and_remove_container(container)


def clean_amqp(amqp_container):
    reset_erl = 'rabbit:stop(), rabbit_mnesia:reset(), rabbit:start().'
    amqp_container.exec_run(['rabbitmqctl', 'eval', reset_erl])


@pytest.fixture
def amqp_container(request, raw_amqp_container):
    if 'clean_amqp' in request.keywords:
        clean_amqp(raw_amqp_container)
    return raw_amqp_container


def create_django_bootstrap_container(
        image, docker_helper, name, command=None, single_container=False,
        publish_port=True):
    kwargs = {
        'command': command,
        'environment': {
            'SECRET_KEY': 'secret',
            'ALLOWED_HOSTS': 'localhost,127.0.0.1,0.0.0.0',
            'DATABASE_URL': DATABASE_URL,
            'CELERY_BROKER_URL': BROKER_URL,
        },
    }
    if single_container:
        kwargs['environment'].update({
            'CELERY_WORKER': '1',
            'CELERY_BEAT': '1',
        })
    if publish_port:
        kwargs['ports'] = {'8000/tcp': ('127.0.0.1',)}

    return docker_helper.create_container(name, image, **kwargs)


@pytest.fixture
def single_container(
        django_bootstrap_image, docker_helper, db_container, amqp_container):
    container = create_django_bootstrap_container(
        django_bootstrap_image, docker_helper, 'web', single_container=True)
    docker_helper.start_container(container)
    wait_for_log_line(container, r'Booting worker')
    wait_for_log_line(container, r'celery@\w+ ready')
    wait_for_log_line(container, r'beat: Starting\.\.\.')
    yield container
    docker_helper.stop_and_remove_container(container)


@pytest.fixture
def web_only_container(
        django_bootstrap_image, docker_helper, db_container, amqp_container):
    container = create_django_bootstrap_container(
        django_bootstrap_image, docker_helper, 'web')
    docker_helper.start_container(container)
    wait_for_log_line(container, r'Booting worker')
    yield container
    docker_helper.stop_and_remove_container(container)


@pytest.fixture(params=['single_container', 'web_only_container'])
def web_container(request):
    yield request.getfixturevalue(request.param)


@pytest.fixture
def worker_only_container(
        django_bootstrap_image, docker_helper, amqp_container):
    container = create_django_bootstrap_container(
        django_bootstrap_image, docker_helper, 'worker',
        command=['celery', 'worker'], publish_port=False)
    docker_helper.start_container(container)
    wait_for_log_line(container, r'celery@\w+ ready')
    yield container
    docker_helper.stop_and_remove_container(container)


@pytest.fixture(params=['single_container', 'worker_only_container'])
def worker_container(request):
    yield request.getfixturevalue(request.param)


@pytest.fixture
def beat_only_container(django_bootstrap_image, docker_helper, amqp_container):
    container = create_django_bootstrap_container(
        django_bootstrap_image, docker_helper, 'beat',
        command=['celery', 'beat'], publish_port=False)
    docker_helper.start_container(container)
    wait_for_log_line(container, r'beat: Starting\.\.\.')
    yield container
    docker_helper.stop_and_remove_container(container)


@pytest.fixture(params=['single_container', 'beat_only_container'])
def beat_container(request):
    yield request.getfixturevalue(request.param)


@pytest.fixture
def web_client(docker_helper, web_container):
    port = docker_helper.get_container_host_port(web_container, '8000/tcp')
    with requests.Session() as session:
        def client(path, method='GET', **kwargs):
            return session.request(
                method, 'http://127.0.0.1:{}{}'.format(port, path), **kwargs)

        yield client


class TestWeb(object):
    def test_expected_processes(self, web_only_container):
        """
        When the container is running, there should be 5 running processes:
        tini, the Nginx master and worker, and the Gunicorn master and worker.
        """
        ps_data = list_container_processes(web_only_container)

        assert_that(ps_data, HasLength(5))

        assert_that(ps_data.pop(0), Equals(
            ['1', 'root',
             'tini -- django-entrypoint.sh mysite.wsgi:application']))

        # The next process we have no control over the start order or PIDs...
        ps_data = [data[1:] for data in ps_data]  # Ignore the PIDs
        # Sometimes this process shows up. Ignore it.
        ps_data = [data for data in ps_data
                   if data != ['django', '/bin/sh /sbin/ldconfig -p']]
        assert_that(ps_data, MatchesSetwise(*map(Equals, [
            ['root', 'nginx: master process nginx -g daemon off;'],
            ['nginx', 'nginx: worker process'],
            ['django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117'],
            # No obvious way to differentiate Gunicorn master from worker
            ['django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117'],
        ])))

    def test_expected_processes_single_container(self, single_container):
        """
        When the container is running, there should be 7 running processes:
        tini, the Nginx master and worker, the Gunicorn master and worker, and
        the Celery worker ("solo", non-forking) and beat processes.
        """
        ps_data = list_container_processes(single_container)

        assert_that(ps_data, HasLength(7))

        assert_that(ps_data.pop(0), Equals(
            ['1', 'root',
             'tini -- django-entrypoint.sh mysite.wsgi:application']))

        # The next process we have no control over the start order or PIDs...
        ps_data = [data[1:] for data in ps_data]  # Ignore the PIDs
        # Sometimes this process shows up. Ignore it.
        ps_data = [data for data in ps_data
                   if data != ['django', '/bin/sh /sbin/ldconfig -p']]
        assert_that(ps_data, MatchesSetwise(*map(Equals, [
            ['root', 'nginx: master process nginx -g daemon off;'],
            ['nginx', 'nginx: worker process'],
            ['django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117'],
            # No obvious way to differentiate Gunicorn master from worker
            ['django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117'],
            ['django',
             '/usr/local/bin/python /usr/local/bin/celery worker --pool=solo '
             '--pidfile worker.pid --concurrency 1'],
            ['django',
             '/usr/local/bin/python /usr/local/bin/celery beat --pidfile '
             'beat.pid'],
        ])))

    @pytest.mark.clean_db
    def test_database_tables_created(self, db_container, web_container):
        """
        When the web container is running, a migration should have completed
        and there should be some tables in the database.
        """
        psql_output = db_container.exec_run(
            ['psql', '-qtA', '--dbname', 'mysite', '-c',
             ('SELECT COUNT(*) FROM information_schema.tables WHERE '
              "table_schema='public';")],
            user='postgres').decode('utf-8')

        count = int(psql_output.strip())
        assert_that(count, GreaterThan(0))

    def test_admin_site_live(self, web_client):
        """
        When we get the /admin/ path, we should receive some HTML for the
        Django admin interface.
        """
        response = web_client('/admin/')

        assert_that(response.headers['Content-Type'],
                    Equals('text/html; charset=utf-8'))
        assert_that(response.text,
                    Contains('<title>Log in | Django site admin</title>'))

    def test_nginx_access_logs(self, web_container, web_client):
        """
        When a request has been made to the container, Nginx logs access logs
        to stdout
        """
        # Wait a little bit so that previous tests' requests have been written
        # to the log.
        time.sleep(0.2)
        before_lines = output_lines(
            web_container.logs(stdout=True, stderr=False))

        # Make a request to see the logs for it
        web_client('/')

        # Wait a little bit so that our request has been written to the log.
        time.sleep(0.2)
        after_lines = output_lines(
            web_container.logs(stdout=True, stderr=False))

        new_lines = after_lines[len(before_lines):]
        assert_that(len(new_lines), GreaterThan(0))

        # Find the Nginx log line
        nginx_lines = [l for l in new_lines if re.match(r'^\{ "time": .+', l)]
        assert_that(nginx_lines, HasLength(1))

        now = datetime.now(timezone.utc)
        assert_that(json.loads(nginx_lines[0]), MatchesDict({
            # Assert time is valid and recent
            'time': After(iso8601.parse_date, MatchesAll(
                MatchesAny(LessThan(now), Equals(now)),
                MatchesAny(GreaterThan(now - timedelta(seconds=5)))
            )),

            'request': Equals('GET / HTTP/1.1'),
            'status': Equals(404),
            'body_bytes_sent': GreaterThan(0),
            'request_time': LessThan(1.0),
            'http_referer': Equals(''),

            # Assert remote_addr is an IPv4 (roughly)
            'remote_addr': MatchesRegex(
                r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'),
            'http_host': MatchesRegex(r'^127.0.0.1:\d{4,5}$'),
            'http_user_agent': MatchesRegex(r'^python-requests/'),

            # Not very interesting empty fields
            'remote_user': Equals(''),
            'http_via': Equals(''),
            'http_x_forwarded_proto': Equals(''),
            'http_x_forwarded_for': Equals(''),
        }))

    def test_static_file(self, web_client):
        """
        When a static file is requested, Nginx should serve the file with the
        correct mime type.
        """
        response = web_client('/static/admin/css/base.css')

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.text, Contains('DJANGO Admin styles'))

    def test_manifest_static_storage_file(self, web_container, web_client):
        """
        When a static file that was processed by Django's
        ManifestStaticFilesStorage system is requested, that file should be
        served with a far-future 'Cache-Control' header.
        """
        hashed_svg = web_container.exec_run(
            ['find', 'static/admin/img', '-regextype', 'posix-egrep', '-regex',
             '.*\.[a-f0-9]{12}\.svg$'])
        test_file = output_lines(hashed_svg)[0]

        response = web_client('/' + test_file)

        assert_that(response.headers['Content-Type'], Equals('image/svg+xml'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_django_compressor_js_file(self, web_container, web_client):
        """
        When a static JavaScript file that was processed by django_compressor
        is requested, that file should be served with a far-future
        'Cache-Control' header.
        """
        compressed_js = web_container.exec_run(
            ['find', 'static/CACHE/js', '-name', '*.js'])
        test_file = output_lines(compressed_js)[0]

        response = web_client('/' + test_file)

        assert_that(response.headers['Content-Type'],
                    Equals('application/javascript'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_django_compressor_css_file(self, web_container, web_client):
        """
        When a static CSS file that was processed by django_compressor is
        requested, that file should be served with a far-future 'Cache-Control'
        header.
        """
        compressed_js = web_container.exec_run(
            ['find', 'static/CACHE/css', '-name', '*.css'])
        test_file = output_lines(compressed_js)[0]

        response = web_client('/' + test_file)

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_gzip_css_compressed(self, web_container, web_client):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should be served gzipped.
        """
        css_to_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '+1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = web_client('/' + test_file,
                              headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Content-Encoding'], Equals('gzip'))
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_woff_not_compressed(self, web_container, web_client):
        """
        When a .woff file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should not be served gzipped as it is already a compressed format.
        """
        woff_to_not_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.woff', '-size', '+1024c'])
        test_file = output_lines(woff_to_not_gzip)[0]

        response = web_client('/' + test_file,
                              headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'],
                    Equals('application/font-woff'))
        assert_that(response.headers, MatchesAll(
            Not(Contains('Content-Encoding')),
            Not(Contains('Vary')),
        ))

    def test_gzip_accept_encoding_respected(self, web_container, web_client):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header does not list gzip as an accepted encoding,
        the file should not be served gzipped, but the 'Vary' header should be
        set to 'Accept-Encoding'.
        """
        css_to_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '+1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = web_client('/' + test_file,
                              headers={'Accept-Encoding': ''})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers, Not(Contains('Content-Encoding')))
        # The Vary header should be set if there is a *possibility* that this
        # file will be served with a different encoding.
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_via_compressed(self, web_container, web_client):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding and the
        'Via' header is set, the file should be served gzipped.
        """
        css_to_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '+1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = web_client(
            '/' + test_file,
            headers={'Accept-Encoding': 'gzip', 'Via': 'Internet.org'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Content-Encoding'], Equals('gzip'))
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_small_file_not_compressed(self, web_container, web_client):
        """
        When a CSS file smaller than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should not be served gzipped.
        """
        css_to_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '-1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = web_client('/' + test_file,
                              headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers, MatchesAll(
            Not(Contains('Content-Encoding')),
            Not(Contains('Vary')),
        ))


class TestCeleryWorker(object):
    def test_expected_processes(self, worker_only_container):
        """
        When the container is running, there should be 3 running processes:
        tini, and the Celery worker master and worker.
        """
        ps_data = list_container_processes(worker_only_container)

        assert_that(ps_data, HasLength(3))

        assert_that(ps_data.pop(0), Equals(
            ['1', 'root',
             'tini -- django-entrypoint.sh celery worker']))

        # The next process we have no control over the start order or PIDs...
        ps_data = [data[1:] for data in ps_data]  # Ignore the PIDs
        assert_that(ps_data, MatchesSetwise(*map(Equals, [
            ['django',
             '/usr/local/bin/python /usr/local/bin/celery worker '
             '--concurrency 1'],
            # No obvious way to differentiate Celery master from worker
            ['django',
             '/usr/local/bin/python /usr/local/bin/celery worker '
             '--concurrency 1'],
        ])))

    @pytest.mark.clean_amqp
    def test_amqp_queues_created(self, amqp_container, worker_container):
        """
        When the worker container is running, the three default Celery queues
        should have been created in RabbitMQ.
        """
        rabbitmq_output = amqp_container.exec_run(
            ['rabbitmqctl', '-q', 'list_queues', '-p', '/mysite'])
        rabbitmq_lines = output_lines(rabbitmq_output)
        rabbitmq_data = [line.split(None, 1) for line in rabbitmq_lines]

        assert_that(rabbitmq_data, HasLength(3))
        assert_that(rabbitmq_data, MatchesSetwise(*map(MatchesListwise, (
            [Equals('celery'), Equals('0')],
            [MatchesRegex(r'^celeryev\..+'), Equals('0')],
            [MatchesRegex(r'^celery@.+\.celery\.pidbox$'), Equals('0')],
        ))))


class TestCeleryBeat(object):
    def test_expected_processes(self, beat_only_container):
        """
        When the container is running, there should be 2 running processes:
        tini, and the Celery beat process.
        """
        ps_data = list_container_processes(beat_only_container)

        assert_that(ps_data, HasLength(2))
        assert_that(ps_data[0], Equals(
            ['1', 'root', 'tini -- django-entrypoint.sh celery beat']))
        # We don't know what PID we will get, so don't check it
        assert_that(ps_data[1][1:], Equals(
            ['django', '/usr/local/bin/python /usr/local/bin/celery beat']))
