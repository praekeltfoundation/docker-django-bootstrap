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
    AfterPreprocessing as After, Contains, Equals, GreaterThan, Is, LessThan,
    MatchesAll, MatchesAny, MatchesDict, MatchesRegex, Not)

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


def pull_image_if_not_found(images, image):
    try:
        images.get(image)
    except docker.errors.ImageNotFound:
        images.pull(image)


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


class TestContainer(unittest.TestCase):
    TEST_IMAGE = 'mysite:py3'

    @classmethod
    def setUpClass(cls):
        # Set up a mini-Docker Compose
        cls.client = docker.client.from_env()
        cls.network = cls.client.networks.create(
            resource_name('default'), driver='bridge')
        cls.services = {}

        cls.setup_db()
        cls.setup_amqp()
        cls.setup_web()
        cls.setup_worker()
        cls.setup_beat()

    @classmethod
    def create_service_container(cls, name, image, **kwargs):
        assert name not in cls.services

        container_name = resource_name(name)
        print("Creating container '{}'...".format(container_name))
        container = cls.client.containers.create(
            image, name=container_name, detach=True, network=cls.network.id,
            **kwargs)

        # FIXME: Hack to make sure the container has the right network aliases.
        # If we don't specify a network when the container is created then the
        # default bridge network is attached which we don't want.
        cls.network.disconnect(container)
        cls.network.connect(container, aliases=[name])

        cls.services[name] = container

    @classmethod
    def start_service_container(cls, name, log_line_pattern):
        assert name in cls.services

        container = cls.services[name]
        print("Starting container '{}'...".format(container.name))
        container.start()
        print(wait_for_log_line(container, log_line_pattern))
        container.reload()
        print("Container status: '{}'".format(container.status))
        assert container.status == 'running'
        print()

    @classmethod
    def stop_and_remove_service_container(
            cls, name, stop_timeout=5, remove_force=True):
        assert name in cls.services

        container = cls.services[name]
        print("Stopping container '{}'...".format(container.name))
        container.stop(timeout=stop_timeout)
        print("Removing container '{}'...".format(container.name))
        container.remove(force=remove_force)
        print()

    @classmethod
    def setup_db(cls):
        pull_image_if_not_found(cls.client.images, POSTGRES_IMAGE)

        cls.create_service_container(
            POSTGRES_PARAMS['service'], POSTGRES_IMAGE, environment={
                'POSTGRES_DB': POSTGRES_PARAMS['db'],
                'POSTGRES_USER': POSTGRES_PARAMS['user'],
                'POSTGRES_PASSWORD': POSTGRES_PARAMS['password'],
            })
        cls.start_service_container(
            POSTGRES_PARAMS['service'],
            r'database system is ready to accept connections')

    @classmethod
    def setup_amqp(cls):
        pull_image_if_not_found(cls.client.images, RABBITMQ_IMAGE)

        cls.create_service_container(
            RABBITMQ_PARAMS['service'], RABBITMQ_IMAGE, environment={
                'RABBITMQ_DEFAULT_VHOST': RABBITMQ_PARAMS['vhost'],
                'RABBITMQ_DEFAULT_USER': RABBITMQ_PARAMS['user'],
                'RABBITMQ_DEFAULT_PASS': RABBITMQ_PARAMS['password'],
            })
        cls.start_service_container(
            RABBITMQ_PARAMS['service'], r'Server startup complete')

    @classmethod
    def create_web_service_container(
            cls, name, command=None, publish_port=True):
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

        cls.create_service_container(name, cls.TEST_IMAGE, **kwargs)

    @classmethod
    def setup_web(cls):
        cls.create_web_service_container('web')
        cls.start_service_container('web', r'Booting worker')

        # FIXME: Bit of a hack to get the port number on the host
        inspection = cls.client.api.inspect_container(cls.services['web'].id)
        cls.web_port = (
            inspection['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort'])

    @classmethod
    def setup_worker(cls):
        cls.create_web_service_container(
            'worker', command=['celery', 'worker'], publish_port=False)
        cls.start_service_container('worker', r'celery@\w+ ready')

    @classmethod
    def setup_beat(cls):
        cls.create_web_service_container(
            'beat', command=['celery', 'beat'], publish_port=False)
        cls.start_service_container('beat', r'beat: Starting\.\.\.')

    @classmethod
    def tearDownClass(cls):
        # Remove all containers
        for service in cls.services.keys():
            cls.stop_and_remove_service_container(service)

        # Remove the network
        cls.network.remove()

    def get(self, path, **kwargs):
        return requests.get(
            'http://127.0.0.1:{}{}'.format(self.web_port, path), **kwargs)

    def test_admin_site_live(self):
        """
        When we get the /admin/ path, we should receive some HTML for the
        Django admin interface.
        """
        response = self.get('/admin/')

        assert_that(response.text,
                    Contains('<title>Log in | Django site admin</title>'))

    def test_nginx_access_logs(self):
        """
        When a request has been made to the container, Nginx logs access logs
        to stdout
        """
        logs = (self.services['web']
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


if __name__ == '__main__':
    # FIXME: Maybe pytest is better at this
    if len(sys.argv) > 1:
        TestContainer.TEST_IMAGE = sys.argv.pop()

    unittest.main()
