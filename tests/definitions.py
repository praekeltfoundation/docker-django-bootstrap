import os
import time

import pytest

from seaworthy.client import wait_for_response
from seaworthy.containers.postgresql import PostgreSQLContainer
from seaworthy.containers.rabbitmq import RabbitMQContainer
from seaworthy.definitions import ContainerDefinition
from seaworthy.ps import list_container_processes
from seaworthy.utils import output_lines


DDB_IMAGE = pytest.config.getoption('--django-bootstrap-image')

DEFAULT_WAIT_TIMEOUT = int(os.environ.get('DEFAULT_WAIT_TIMEOUT', '30'))

db_container = PostgreSQLContainer(wait_timeout=DEFAULT_WAIT_TIMEOUT)

amqp_container = RabbitMQContainer(
    vhost='/mysite', wait_timeout=DEFAULT_WAIT_TIMEOUT)

default_env = env = {
    'SECRET_KEY': 'secret',
    'ALLOWED_HOSTS': 'localhost,127.0.0.1,0.0.0.0',
    'CELERY_BROKER_URL': amqp_container.broker_url(),
    'DATABASE_URL': db_container.database_url(),
}


class GunicornContainer(ContainerDefinition):
    WAIT_TIMEOUT = DEFAULT_WAIT_TIMEOUT

    def list_processes(self):
        return list_container_processes(self.inner())

    def exec_run(self, args):
        return output_lines(self.inner().exec_run(args))

    def exec_find(self, params):
        return self.exec_run(['find'] + params)

    def wait_for_start(self):
        # Override wait_for_start to wait for the health check to succeed.
        # Still wait for log lines to match because we also need to wait for
        # Celery to start in the single-container setup.
        start = time.monotonic()
        super().wait_for_start()

        remaining = self.wait_timeout - (time.monotonic() - start)
        wait_for_response(self.http_client(), remaining, path='/health/',
                          expected_status_code=200)

    @classmethod
    def for_fixture(cls, name, wait_lines, command=None, env_extra={}):
        env = dict(default_env)
        env.update(env_extra)
        kwargs = {
            'command': command,
            'environment': env,
            # Add a tmpfs mount at /app/media so that we can test ownership of
            # the directory is set. Normally a proper volume would be mounted
            # but the effect is the same.
            'tmpfs': {'/app/media': 'uid=0'},
            'ports': {'8000/tcp': ('127.0.0.1',)}
        }

        return cls(name, DDB_IMAGE, wait_lines, create_kwargs=kwargs)

    def pytest_fixture(self, name):
        return super().pytest_fixture(
            name, dependencies=('db_container', 'amqp_container'))

    @classmethod
    def make_fixture(cls, fixture_name, name, *args, **kw):
        return cls.for_fixture(name, *args, **kw).pytest_fixture(fixture_name)


class CeleryContainer(ContainerDefinition):
    WAIT_TIMEOUT = DEFAULT_WAIT_TIMEOUT

    def list_processes(self):
        return list_container_processes(self.inner())

    @classmethod
    def for_fixture(cls, celery_command, wait_lines):
        kwargs = {
            'command': ['celery', celery_command],
            'environment': default_env,
        }
        return cls(celery_command, DDB_IMAGE, wait_lines, create_kwargs=kwargs)


single_container = GunicornContainer.for_fixture(
    'web', [r'Booting worker', r'celery@\w+ ready', r'beat: Starting\.\.\.'],
    env_extra={'CELERY_WORKER': '1', 'CELERY_BEAT': '1'})


web_container = GunicornContainer.for_fixture('web', [r'Booting worker'])


worker_container = CeleryContainer.for_fixture('worker', [r'celery@\w+ ready'])


beat_container = CeleryContainer.for_fixture('beat', [r'beat: Starting\.\.\.'])


def make_combined_fixture(base):
    """
    This creates a parameterised fixture that allows us to run a single test
    with both a special-purpose container and the all-in-one container.
    """
    name = '{}_container'.format(base)
    fixtures = ['single_container', '{}_only_container'.format(base)]

    @pytest.fixture(name=name, params=fixtures)
    def containers(request):
        yield request.getfixturevalue(request.param)

    return containers
