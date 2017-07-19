import pytest
import requests

from docker_helper import DockerHelper, wait_for_log_line


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
        for line in wait_lines:
            wait_for_log_line(container, line)
        yield container
        docker_helper.stop_and_remove_container(container)
    return app_container


single_container = make_app_container(
    'single_container', 'web', ['db_container', 'amqp_container'],
    [r'Booting worker', r'celery@\w+ ready', 'beat: Starting\.\.\.'],
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
