import os

import pytest

from seaworthy.definitions import ContainerDefinition
from seaworthy.containers.postgresql import PostgreSQLContainer
from seaworthy.containers.rabbitmq import RabbitMQContainer
from seaworthy.ps import list_container_processes
from seaworthy.pytest.fixtures import clean_container_fixtures
from seaworthy.logs import output_lines


DDB_IMAGE = pytest.config.getoption('--django-bootstrap-image')

DEFAULT_WAIT_TIMEOUT = int(os.environ.get('DEFAULT_WAIT_TIMEOUT', '30'))


raw_db_container, db_container = clean_container_fixtures(
    PostgreSQLContainer(wait_timeout=DEFAULT_WAIT_TIMEOUT), 'db_container',
    scope='module')


raw_amqp_container, amqp_container = clean_container_fixtures(
    RabbitMQContainer(vhost='/mysite', wait_timeout=DEFAULT_WAIT_TIMEOUT),
    'amqp_container', scope='module')


class DjangoBootstrapContainer(ContainerDefinition):
    WAIT_TIMEOUT = DEFAULT_WAIT_TIMEOUT

    def list_processes(self):
        return list_container_processes(self.inner())

    def exec_find(self, params):
        return output_lines(self.inner().exec_run(['find'] + params))

    @classmethod
    def for_fixture(
            cls, request, name, wait_lines, command=None, env_extra={},
            publish_port=True, wait_timeout=None):
        docker_helper = request.getfixturevalue('docker_helper')
        amqp_container = request.getfixturevalue('amqp_container')
        db_container = request.getfixturevalue('db_container')
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

        return cls(
            name, DDB_IMAGE, wait_lines, wait_timeout, kwargs,
            helper=docker_helper.containers)

    @classmethod
    def make_fixture(cls, fixture_name, name, *args, **kw):
        @pytest.fixture(name=fixture_name)
        def fixture(request):
            with cls.for_fixture(request, name, *args, **kw) as container:
                yield container
        return fixture


single_container = DjangoBootstrapContainer.make_fixture(
    'single_container', 'web',
    [r'Booting worker', r'celery@\w+ ready', r'beat: Starting\.\.\.'],
    env_extra={'CELERY_WORKER': '1', 'CELERY_BEAT': '1'})


web_only_container = DjangoBootstrapContainer.make_fixture(
    'web_only_container',  'web', [r'Booting worker'])


worker_only_container = DjangoBootstrapContainer.make_fixture(
    'worker_only_container', 'worker', [r'celery@\w+ ready'],
    command=['celery', 'worker'], publish_port=False)


beat_only_container = DjangoBootstrapContainer.make_fixture(
    'beat_only_container', 'beat', [r'beat: Starting\.\.\.'],
    command=['celery', 'beat'], publish_port=False)


def make_multi_container(name, containers):
    @pytest.fixture(name=name, params=containers)
    def containers(request):
        yield request.getfixturevalue(request.param)
    return containers


web_container = make_multi_container(
    'web_container', ['single_container', 'web_only_container'])

worker_container = make_multi_container(
    'worker_container', ['single_container', 'worker_only_container'])

beat_container = make_multi_container(
    'beat_container', ['single_container', 'beat_only_container'])


__all__ = [
    'raw_db_container', 'db_container', 'raw_amqp_container',
    'amqp_container', 'single_container', 'web_only_container',
    'worker_only_container', 'beat_only_container', 'web_container',
    'worker_container', 'beat_container']
