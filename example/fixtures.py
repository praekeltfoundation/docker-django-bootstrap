import os

import pytest

from seaworthy.definitions import ContainerDefinition
from seaworthy.containers.postgresql import PostgreSQLContainer
from seaworthy.containers.rabbitmq import RabbitMQContainer
from seaworthy.ps import list_container_processes
from seaworthy.logs import output_lines


DDB_IMAGE = pytest.config.getoption('--django-bootstrap-image')

DEFAULT_WAIT_TIMEOUT = int(os.environ.get('DEFAULT_WAIT_TIMEOUT', '30'))

db_container = PostgreSQLContainer(wait_timeout=DEFAULT_WAIT_TIMEOUT)


amqp_container = RabbitMQContainer(
    vhost='/mysite', wait_timeout=DEFAULT_WAIT_TIMEOUT)


class DjangoBootstrapContainer(ContainerDefinition):
    WAIT_TIMEOUT = DEFAULT_WAIT_TIMEOUT

    def list_processes(self):
        return list_container_processes(self.inner())

    def exec_find(self, params):
        return output_lines(self.inner().exec_run(['find'] + params))

    @classmethod
    def for_fixture(
            cls, name, wait_lines, command=None, env_extra={},
            publish_port=True, wait_timeout=None):
        env = {
            'SECRET_KEY': 'secret',
            'ALLOWED_HOSTS': 'localhost,127.0.0.1,0.0.0.0',
            'CELERY_BROKER_URL': amqp_container.broker_url(),
            'DATABASE_URL': db_container.database_url(),
        }
        env.update(env_extra)
        kwargs = {
            'command': command,
            'environment': env,
        }
        if publish_port:
            kwargs['ports'] = {'8000/tcp': ('127.0.0.1',)}

        return cls(name, DDB_IMAGE, wait_lines, wait_timeout, kwargs)

    def pytest_fixture(self, name):
        return super().pytest_fixture(
            name, dependencies=('db_container', 'amqp_container'))

    @classmethod
    def make_fixture(cls, fixture_name, name, *args, **kw):
        return cls.for_fixture(name, *args, **kw).pytest_fixture(fixture_name)


single_container = DjangoBootstrapContainer.for_fixture(
    'web', [r'Booting worker', r'celery@\w+ ready', r'beat: Starting\.\.\.'],
    env_extra={'CELERY_WORKER': '1', 'CELERY_BEAT': '1'})


web_container = DjangoBootstrapContainer.for_fixture(
    'web', [r'Booting worker'])


worker_container = DjangoBootstrapContainer.for_fixture(
    'worker', [r'celery@\w+ ready'],
    command=['celery', 'worker'], publish_port=False)


beat_container = DjangoBootstrapContainer.for_fixture(
    'beat', [r'beat: Starting\.\.\.'],
    command=['celery', 'beat'], publish_port=False)


def make_multi_fixture(name, fixtures):
    @pytest.fixture(name=name, params=fixtures)
    def containers(request):
        yield request.getfixturevalue(request.param)
    return containers


def make_combined_fixture(base):
    return make_multi_fixture(
        '{}_container'.format(base),
        ['single_container', '{}_only_container'.format(base)])
