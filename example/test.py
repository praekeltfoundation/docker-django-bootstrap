#!/usr/bin/env python3
import json
import re
import sys
import _thread as thread
import threading
import unittest
from datetime import datetime, timedelta, timezone

import docker
import iso8601
import requests
from testtools.assertions import assert_that
from testtools.matchers import (
    AfterPreprocessing as After, Contains, Equals, GreaterThan, HasLength, Is,
    LessThan, MatchesAll, MatchesAny, MatchesDict, MatchesListwise,
    MatchesRegex, MatchesSetwise, Not)

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
DJANGO_BOOTSTRAP_IMAGE = 'mysite:py3'
DATABASE_URL = (
    'postgres://{user}:{password}@{service}/{db}'.format(**POSTGRES_PARAMS))
BROKER_URL = (
    'amqp://{user}:{password}@{service}/{vhost}'.format(**RABBITMQ_PARAMS))


def resource_name(name, namespace='test'):
    return '{}_{}'.format(namespace, name)


def quit_function(fn_name):
    # https://stackoverflow.com/a/31667005
    print('{} took too long'.format(fn_name), file=sys.stderr)
    sys.stderr.flush()  # Python 3 stderr is likely buffered.
    # FIXME: Interrupting the main thread is hacky
    thread.interrupt_main()  # raises KeyboardInterrupt


def exit_after(s):
    """
    Use as decorator to exit process if function takes longer than s seconds
    https://stackoverflow.com/a/31667005
    """
    def outer(fn):
        def inner(*args, **kwargs):
            timer = threading.Timer(s, quit_function, args=[fn.__name__])
            timer.start()
            try:
                result = fn(*args, **kwargs)
            finally:
                timer.cancel()
            return result
        return inner
    return outer


@exit_after(10)
def wait_for_log_line(container, pattern):
    for line in container.logs(stream=True):
        line = line.decode('utf-8').rstrip()  # Drop the trailing newline
        if re.search(pattern, line):
            return line


def output_lines(raw_output, encoding='utf-8'):
    decoded = raw_output.decode(encoding)
    lines = decoded.split('\n')
    # Remove extra newline at end of output
    lines.pop()
    return lines


def list_container_processes(container):
    ps_output = container.exec_run(
        ['ps', 'ax', '-o', 'pid,ruser,command', '--no-headers'])
    ps_lines = output_lines(ps_output)

    ps_data = []
    for line in ps_lines:
        # Tuple of process information: user, PID, name
        parts = line.split(None, 2)
        if not parts[2].startswith('ps ax'):
            ps_data.append((int(parts[0]), parts[1], parts[2]))

    return ps_data


class DockerHelper(object):
    def setup(self):
        self._client = docker.client.from_env()
        self._network = self._client.networks.create(
            resource_name('default'), driver='bridge')
        self._container_ids = []

    def teardown(self):
        # Remove all containers
        for container_id in self._container_ids:
            # Check if the container exists before trying to remove it
            try:
                container = self._client.containers.get(container_id)
            except docker.errors.NotFound:
                continue

            print("Warning container '{}' was still running".format(
                container.name))

            self.stop_and_remove_container(container)

        # Remove the network
        self._network.remove()

    def create_container(self, name, image, **kwargs):
        container_name = resource_name(name)
        print("Creating container '{}'...".format(container_name))
        container = self._client.containers.create(
            image, name=container_name, detach=True, network=self._network.id,
            **kwargs)

        # FIXME: Hack to make sure the container has the right network aliases.
        # If we don't specify a network when the container is created then the
        # default bridge network is attached which we don't want.
        self._network.disconnect(container)
        self._network.connect(container, aliases=[name])

        # Keep a reference to created containers to make sure they are cleaned
        # up
        self._container_ids.append(container.id)

        return container

    def start_container(self, container, log_line_pattern):
        print("Starting container '{}'...".format(container.name))
        container.start()
        print(wait_for_log_line(container, log_line_pattern))
        container.reload()
        print("Container status: '{}'".format(container.status))
        assert container.status == 'running'
        print()

    def stop_and_remove_container(
            self, container, stop_timeout=5, remove_force=True):
        print("Stopping container '{}'...".format(container.name))
        container.stop(timeout=stop_timeout)
        print("Removing container '{}'...".format(container.name))
        container.remove(force=remove_force)
        print()

    def pull_image_if_not_found(self, image):
        try:
            self._client.images.get(image)
            print("Image '{}' found".format(image))
        except docker.errors.ImageNotFound:
            print("Pulling image '{}'...".format(image))
            self._client.images.pull(image)

    def get_container_host_port(self, container, container_port, index=0):
        # FIXME: Bit of a hack to get the port number on the host
        inspection = self._client.api.inspect_container(container.id)
        return (inspection['NetworkSettings']['Ports']
                [container_port][index]['HostPort'])


docker_helper = DockerHelper()
infra_containers = {}


def setUpModule():
    docker_helper.setup()
    setup_db()
    setup_amqp()


def setup_db():
    docker_helper.pull_image_if_not_found(POSTGRES_IMAGE)

    container = docker_helper.create_container(
        POSTGRES_PARAMS['service'], POSTGRES_IMAGE, environment={
            'POSTGRES_DB': POSTGRES_PARAMS['db'],
            'POSTGRES_USER': POSTGRES_PARAMS['user'],
            'POSTGRES_PASSWORD': POSTGRES_PARAMS['password'],
        })
    docker_helper.start_container(
        container,
        r'database system is ready to accept connections')

    infra_containers['db'] = container


def setup_amqp():
    docker_helper.pull_image_if_not_found(RABBITMQ_IMAGE)

    container = docker_helper.create_container(
        RABBITMQ_PARAMS['service'], RABBITMQ_IMAGE, environment={
            'RABBITMQ_DEFAULT_VHOST': RABBITMQ_PARAMS['vhost'],
            'RABBITMQ_DEFAULT_USER': RABBITMQ_PARAMS['user'],
            'RABBITMQ_DEFAULT_PASS': RABBITMQ_PARAMS['password'],
        })
    docker_helper.start_container(container, r'Server startup complete')

    infra_containers['amqp'] = container


def tearDownModule():
    for container in infra_containers.values():
        docker_helper.stop_and_remove_container(container)
    docker_helper.teardown()


def create_django_bootstrap_container(
        docker_helper, name, command=None, publish_port=True):
    kwargs = {
        'command': command,
        'environment': {
            'SECRET_KEY': 'secret',
            'ALLOWED_HOSTS': 'localhost,127.0.0.1,0.0.0.0',
            'DATABASE_URL': DATABASE_URL,
            'CELERY_BROKER_URL': BROKER_URL,
        },
    }
    if publish_port:
        kwargs['ports'] = {'8000/tcp': ('127.0.0.1',)}

    return docker_helper.create_container(
        name, DJANGO_BOOTSTRAP_IMAGE, **kwargs)


class TestWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web_container = create_django_bootstrap_container(
            docker_helper, 'web')
        docker_helper.start_container(cls.web_container, r'Booting worker')

        cls.web_port = docker_helper.get_container_host_port(
            cls.web_container, '8000/tcp')

    @classmethod
    def tearDownClass(cls):
        docker_helper.stop_and_remove_container(cls.web_container)

    def test_expected_processes(self):
        """
        When the container is running, there should be 5 running processes:
        tini, the Nginx master and worker, and the Gunicorn master and worker.
        """
        ps_data = list_container_processes(self.web_container)

        assert_that(ps_data, HasLength(5))

        assert_that(ps_data.pop(0), Equals(
            (1, 'root',
             'tini -- django-entrypoint.sh mysite.wsgi:application')))

        # The next process we have no control over the start order or PIDs...
        ps_data = [data[1:] for data in ps_data]  # Ignore the PIDs
        assert_that(ps_data, MatchesSetwise(*map(Equals, [
            ('root', 'nginx: master process nginx -g daemon off;'),
            ('nginx', 'nginx: worker process'),
            ('django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117'),
            # No obvious way to differentiate Gunicorn master from worker
            ('django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117'),
        ])))

    def test_database_tables_created(self):
        """
        When the web container is running, a migration should have completed
        and there should be some tables in the database.
        """
        psql_output = infra_containers['db'].exec_run(
            ['psql', '-qtA', '--dbname', 'mysite', '-c',
             ('SELECT COUNT(*) FROM information_schema.tables WHERE '
              "table_schema='public';")],
            user='postgres').decode('utf-8')

        count = int(psql_output.strip())
        assert_that(count, GreaterThan(0))

    def get(self, path, **kwargs):
        return requests.get(
            'http://127.0.0.1:{}{}'.format(self.web_port, path), **kwargs)

    def test_admin_site_live(self):
        """
        When we get the /admin/ path, we should receive some HTML for the
        Django admin interface.
        """
        response = self.get('/admin/')

        assert_that(response.headers['Content-Type'],
                    Equals('text/html; charset=utf-8'))
        assert_that(response.text,
                    Contains('<title>Log in | Django site admin</title>'))

    def test_nginx_access_logs(self):
        """
        When a request has been made to the container, Nginx logs access logs
        to stdout
        """
        logs = (self.web_container
                .logs(stdout=True, stderr=False).decode('utf-8'))

        match = re.search(r'\{ "time": .+', logs)
        assert_that(match, Not(Is(None)))

        access_json = json.loads(match.group(0))

        now = datetime.now(timezone.utc)
        assert_that(access_json, MatchesDict({
            # Assert time is valid and recent
            'time': After(iso8601.parse_date, MatchesAll(
                MatchesAny(LessThan(now), Equals(now)),
                MatchesAny(GreaterThan(now - timedelta(seconds=5)))
            )),

            # FIXME: These assertions rely on the previous test running first
            'request': Equals('GET /admin/ HTTP/1.1'),
            'status': Equals(302),
            'body_bytes_sent': Equals(0),
            'request_time': LessThan(1.0),
            'http_referer': Equals(''),

            # Assert remote_addr is an IPv4 (roughly)
            'remote_addr': MatchesRegex(
                r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'),
            'http_host': Equals('127.0.0.1:{}'.format(self.web_port)),
            'http_user_agent': MatchesRegex(r'^python-requests/'),

            # Not very interesting empty fields
            'remote_user': Equals(''),
            'http_via': Equals(''),
            'http_x_forwarded_proto': Equals(''),
            'http_x_forwarded_for': Equals(''),
        }))

    def test_static_file(self):
        """
        When a static file is requested, Nginx should serve the file with the
        correct mime type.
        """
        response = self.get('/static/admin/css/base.css')

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.text, Contains('DJANGO Admin styles'))

    def test_manifest_static_storage_file(self):
        """
        When a static file that was processed by Django's
        ManifestStaticFilesStorage system is requested, that file should be
        served with a far-future 'Cache-Control' header.
        """
        hashed_svg = self.web_container.exec_run(
            ['find', 'static/admin/img', '-regextype', 'posix-egrep', '-regex',
             '.*\.[a-f0-9]{12}\.svg$'])
        test_file = output_lines(hashed_svg)[0]

        response = self.get('/' + test_file)

        assert_that(response.headers['Content-Type'], Equals('image/svg+xml'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_django_compressor_js_file(self):
        """
        When a static JavaScript file that was processed by django_compressor
        is requested, that file should be served with a far-future
        'Cache-Control' header.
        """
        compressed_js = self.web_container.exec_run(
            ['find', 'static/CACHE/js', '-name', '*.js'])
        test_file = output_lines(compressed_js)[0]

        response = self.get('/' + test_file)

        assert_that(response.headers['Content-Type'],
                    Equals('application/javascript'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_django_compressor_css_file(self):
        """
        When a static CSS file that was processed by django_compressor is
        requested, that file should be served with a far-future 'Cache-Control'
        header.
        """
        compressed_js = self.web_container.exec_run(
            ['find', 'static/CACHE/css', '-name', '*.css'])
        test_file = output_lines(compressed_js)[0]

        response = self.get('/' + test_file)

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_gzip_css_compressed(self):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should be served gzipped.
        """
        css_to_gzip = self.web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '+1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = self.get('/' + test_file,
                            headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Content-Encoding'], Equals('gzip'))
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_woff_not_compressed(self):
        """
        When a .woff file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should not be served gzipped as it is already a compressed format.
        """
        woff_to_not_gzip = self.web_container.exec_run(
            ['find', 'static', '-name', '*.woff', '-size', '+1024c'])
        test_file = output_lines(woff_to_not_gzip)[0]

        response = self.get('/' + test_file,
                            headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'],
                    Equals('application/font-woff'))
        assert_that(response.headers, MatchesAll(
            Not(Contains('Content-Encoding')),
            Not(Contains('Vary')),
        ))

    def test_gzip_accept_encoding_respected(self):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header does not list gzip as an accepted encoding,
        the file should not be served gzipped, but the 'Vary' header should be
        set to 'Accept-Encoding'.
        """
        css_to_gzip = self.web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '+1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = self.get('/' + test_file,
                            headers={'Accept-Encoding': ''})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers, Not(Contains('Content-Encoding')))
        # The Vary header should be set if there is a *possibility* that this
        # file will be served with a different encoding.
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_via_compressed(self):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding and the
        'Via' header is set, the file should be served gzipped.
        """
        css_to_gzip = self.web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '+1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = self.get(
            '/' + test_file,
            headers={'Accept-Encoding': 'gzip', 'Via': 'Internet.org'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Content-Encoding'], Equals('gzip'))
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_small_file_not_compressed(self):
        """
        When a CSS file smaller than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should not be served gzipped.
        """
        css_to_gzip = self.web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '-1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = self.get('/' + test_file,
                            headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers, MatchesAll(
            Not(Contains('Content-Encoding')),
            Not(Contains('Vary')),
        ))


class TestCeleryWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker_container = create_django_bootstrap_container(
            docker_helper, 'worker', command=['celery', 'worker'],
            publish_port=False)
        docker_helper.start_container(
            cls.worker_container, r'celery@\w+ ready')

    @classmethod
    def tearDownClass(cls):
        docker_helper.stop_and_remove_container(cls.worker_container)

    def test_expected_processes(self):
        """
        When the container is running, there should be 3 running processes:
        tini, and the Celery worker master and worker.
        """
        ps_data = list_container_processes(self.worker_container)

        assert_that(ps_data, HasLength(3))

        assert_that(ps_data.pop(0), Equals(
            (1, 'root',
             'tini -- django-entrypoint.sh celery worker')))

        # The next process we have no control over the start order or PIDs...
        ps_data = [data[1:] for data in ps_data]  # Ignore the PIDs
        assert_that(ps_data, MatchesSetwise(*map(Equals, [
            ('django',
             '/usr/local/bin/python /usr/local/bin/celery worker '
             '--concurrency 1'),
            # No obvious way to differentiate Celery master from worker
            ('django',
             '/usr/local/bin/python /usr/local/bin/celery worker '
             '--concurrency 1'),
        ])))

    def test_amqp_queues_created(self):
        """
        When the worker container is running, the three default Celery queues
        should have been created in RabbitMQ.
        """
        rabbitmq_output = infra_containers['amqp'].exec_run(
            ['rabbitmqctl', '-q', 'list_queues', '-p', '/mysite'])
        rabbitmq_lines = output_lines(rabbitmq_output)
        rabbitmq_data = [line.split(None, 1) for line in rabbitmq_lines]

        assert_that(rabbitmq_data, HasLength(3))
        assert_that(rabbitmq_data, MatchesSetwise(*map(MatchesListwise, (
            [Equals('celery'), Equals('0')],
            [MatchesRegex(r'^celeryev\..+'), Equals('0')],
            [MatchesRegex(r'^celery@.+\.celery\.pidbox$'), Equals('0')],
        ))))


class TestCeleryBeat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.beat_container = create_django_bootstrap_container(
            docker_helper, 'beat', command=['celery', 'beat'],
            publish_port=False)
        docker_helper.start_container(
            cls.beat_container, r'beat: Starting\.\.\.')

    @classmethod
    def tearDownClass(cls):
        docker_helper.stop_and_remove_container(cls.beat_container)

    def test_expected_processes(self):
        """
        When the container is running, there should be 2 running processes:
        tini, and the Celery beat process.
        """
        ps_data = list_container_processes(self.beat_container)

        assert_that(ps_data, HasLength(2))
        assert_that(ps_data[0], Equals(
            (1, 'root', 'tini -- django-entrypoint.sh celery beat')))
        # We don't know what PID we will get, so don't check it
        assert_that(ps_data[1][1:], Equals(
            ('django', '/usr/local/bin/python /usr/local/bin/celery beat')))


if __name__ == '__main__':
    # FIXME: Maybe pytest is better at this
    if len(sys.argv) > 1:
        DJANGO_BOOTSTRAP_IMAGE = sys.argv.pop()

    unittest.main()
