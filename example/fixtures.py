import pytest
import requests

from seaworthy.containers.base import ContainerBase
from seaworthy.containers.provided import (
    PostgreSQLContainer, RabbitMQContainer)
from seaworthy.ps import list_container_processes
from seaworthy.pytest.fixtures import clean_container_fixtures
from seaworthy.utils import output_lines


raw_db_container, db_container = clean_container_fixtures(
    PostgreSQLContainer(), 'db_container', scope='module')


raw_amqp_container, amqp_container = clean_container_fixtures(
    RabbitMQContainer(vhost='/mysite'), 'amqp_container', scope='module')


class DjangoBootstrapContainer(ContainerBase):
    def list_processes(self):
        return list_container_processes(self.inner())

    def exec_find(self, params):
        return output_lines(self.inner().exec_run(['find'] + params))


def create_django_bootstrap_container(
        request, name, wait_lines, command=None, single_container=False,
        publish_port=True, other_fixtures=()):
    for fix in other_fixtures:
        request.getfixturevalue(fix)
    image = request.getfixturevalue('django_bootstrap_image')
    # FIXME: Get these URLs in a better way.
    database_url = PostgreSQLContainer().database_url()
    celery_broker_url = RabbitMQContainer(vhost='/mysite').broker_url()
    kwargs = {
        'command': command,
        'environment': {
            'SECRET_KEY': 'secret',
            'ALLOWED_HOSTS': 'localhost,127.0.0.1,0.0.0.0',
            'DATABASE_URL': database_url,
            'CELERY_BROKER_URL': celery_broker_url,
        },
    }
    if single_container:
        kwargs['environment'].update({
            'CELERY_WORKER': '1',
            'CELERY_BEAT': '1',
        })
    if publish_port:
        kwargs['ports'] = {'8000/tcp': ('127.0.0.1',)}

    return DjangoBootstrapContainer(name, image, wait_lines, kwargs)


def container_factory_fixture(factory, name, kwargs, scope='function'):
    @pytest.fixture(name=name, scope=scope)
    def raw_fixture(request, docker_helper):
        container = factory(request, **kwargs)
        container.create_and_start(docker_helper)
        yield container
        container.stop_and_remove(docker_helper)

    return raw_fixture


def make_app_container(
        name, container_name, other_fixtures, wait_lines, command=None,
        single_container=False, publish_port=True):
    return container_factory_fixture(
        create_django_bootstrap_container, name, kwargs={
            'name': container_name,
            'wait_lines': wait_lines,
            'command': command,
            'single_container': single_container,
            'publish_port': publish_port,
            'other_fixtures': other_fixtures,
        })


single_container = make_app_container(
    'single_container', 'web', ['db_container', 'amqp_container'],
    [r'Booting worker', r'celery@\w+ ready', r'beat: Starting\.\.\.'],
    single_container=True)

web_only_container = make_app_container(
    'web_only_container', 'web', ['db_container', 'amqp_container'],
    [r'Booting worker'])

worker_only_container = make_app_container(
    'worker_only_container', 'worker', ['amqp_container'],
    [r'celery@\w+ ready'], command=['celery', 'worker'], publish_port=False)

beat_only_container = make_app_container(
    'beat_only_container', 'beat', ['amqp_container'],
    [r'beat: Starting\.\.\.'], command=['celery', 'beat'], publish_port=False)


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


@pytest.fixture
def web_client(docker_helper, web_container):
    port = web_container.get_host_port('8000/tcp')
    with requests.Session() as session:
        def client(path, method='GET', **kwargs):
            return session.request(
                method, 'http://127.0.0.1:{}{}'.format(port, path), **kwargs)

        yield client


__all__ = [
    'raw_db_container', 'db_container', 'raw_amqp_container',
    'amqp_container', 'single_container', 'web_only_container',
    'worker_only_container', 'beat_only_container', 'web_container',
    'worker_container', 'beat_container', 'web_client']
