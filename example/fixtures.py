import pytest
import requests

from seaworthy import DockerHelper, wait_for_logs_matching
from seaworthy.logs import RegexMatcher
from seaworthy.containers.provided import (
    PostgreSQLContainer, RabbitMQContainer)


def wait_for_logs(container, patterns):
    for pattern in patterns:
        wait_for_logs_matching(container, RegexMatcher(pattern))


@pytest.fixture(scope='module')
def docker_helper():
    docker_helper = DockerHelper()
    docker_helper.setup()
    yield docker_helper
    docker_helper.teardown()


class ContainerDefinition(object):
    def __init__(self, name, image, wait_lines=[], pull_image=False,
                 **create_kwargs):
        self.name = name
        self.image = image
        self.wait_lines = wait_lines
        self.pull_image = pull_image
        self.create_kwargs = create_kwargs

    def create_and_start(self, docker_helper):
        if self.pull_image:
            docker_helper.pull_image_if_not_found(self.image)

        container = docker_helper.create_container(
            self.name, self.image, **self.create_kwargs)
        docker_helper.start_container(container)
        wait_for_logs(container, self.wait_lines)
        return container

    def fixture(self, name, scope='function'):
        @pytest.fixture(name=name, scope=scope)
        def _fixture(docker_helper):
            container = self.create_and_start(docker_helper)
            yield container
            docker_helper.stop_and_remove_container(container)
        return _fixture


def mk_seaworthy_fixture(name, container_cls, scope='function', **kwargs):
    @pytest.fixture(name=name, scope=scope)
    def _fixture(docker_helper):
        container = container_cls(**kwargs)
        container.create_and_start(docker_helper)
        yield container
        container.stop_and_remove(docker_helper)
    return _fixture


raw_db_container = mk_seaworthy_fixture(
    'raw_db_container', PostgreSQLContainer, 'module')


@pytest.fixture
def db_container(request, raw_db_container):
    if 'clean_db' in request.keywords:
        raw_db_container.clean()
    return raw_db_container


raw_amqp_container = mk_seaworthy_fixture(
    'raw_amqp_container', RabbitMQContainer, 'module', vhost='/mysite')


@pytest.fixture
def amqp_container(request, raw_amqp_container):
    if 'clean_amqp' in request.keywords:
        raw_amqp_container.clean()
    return raw_amqp_container


def create_django_bootstrap_container(
        image, docker_helper, name, command=None, single_container=False,
        publish_port=True):
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

    return docker_helper.create_container(name, image, **kwargs)


def make_app_container(
        name, container_name, other_fixtures, wait_lines, command=None,
        single_container=False, publish_port=True):
    @pytest.fixture(name=name)
    def app_container(request, django_bootstrap_image, docker_helper):
        for fix in other_fixtures:
            request.getfixturevalue(fix)
        container = create_django_bootstrap_container(
            django_bootstrap_image, docker_helper, container_name,
            command=command, single_container=single_container,
            publish_port=publish_port)
        docker_helper.start_container(container)
        wait_for_logs(container, wait_lines)
        yield container
        docker_helper.stop_and_remove_container(container)
    return app_container


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
    port = docker_helper.get_container_host_port(web_container, '8000/tcp')
    with requests.Session() as session:
        def client(path, method='GET', **kwargs):
            return session.request(
                method, 'http://127.0.0.1:{}{}'.format(port, path), **kwargs)

        yield client


__all__ = [
    'docker_helper', 'raw_db_container', 'db_container', 'raw_amqp_container',
    'amqp_container', 'single_container', 'web_only_container',
    'worker_only_container', 'beat_only_container', 'web_container',
    'worker_container', 'beat_container', 'web_client']
