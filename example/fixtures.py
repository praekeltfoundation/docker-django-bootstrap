import os
import time

import pytest

from seaworthy.definitions import ContainerDefinition, VolumeDefinition
from seaworthy.containers.postgresql import PostgreSQLContainer
from seaworthy.containers.rabbitmq import RabbitMQContainer
from seaworthy.ps import list_container_processes
from seaworthy.pytest.fixtures import clean_container_fixtures
from seaworthy.logs import output_lines


DDB_IMAGE = pytest.config.getoption('--django-bootstrap-image')
NGINX_IMAGE = pytest.config.getoption('--db-nginx-image')

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
        pods = request.getfixturevalue('pods')
        # FIXME: there are probably better ways to skip these tests
        if pods:
            if request.fixturename in [
                    'web_only_container', 'single_container']:
                pytest.skip()
        else:
            if request.fixturename == 'gunicorn_container':
                pytest.skip()
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
        if pods:
            static_volume = request.getfixturevalue('static_volume')
            media_volume = request.getfixturevalue('media_volume')
            gunicorn_volume = request.getfixturevalue('gunicorn_volume')
            kwargs['volumes'] = {
                static_volume.inner(): {'bind': '/app/static', 'mode': 'rw'},
                media_volume.inner(): {'bind': '/app/media', 'mode': 'rw'},
                gunicorn_volume.inner(): {
                    'bind': '/var/run/gunicorn', 'mode': 'rw'},
            }

        return cls(
            name, DDB_IMAGE, wait_lines, wait_timeout, kwargs,
            helper=docker_helper)

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

gunicorn_container = DjangoBootstrapContainer.make_fixture(
    'gunicorn_container', 'web', [r'Booting worker'], publish_port=False)

beat_only_container = DjangoBootstrapContainer.make_fixture(
    'beat_only_container', 'beat', [r'beat: Starting\.\.\.'],
    command=['celery', 'beat'], publish_port=False)


def make_multi_container(name, containers):
    @pytest.fixture(name=name, params=containers)
    def containers(request):
        yield request.getfixturevalue(request.param)
    return containers


web_container = make_multi_container(
    'web_container',
    ['single_container', 'web_only_container', 'gunicorn_container'])

worker_container = make_multi_container(
    'worker_container', ['single_container', 'worker_only_container'])

beat_container = make_multi_container(
    'beat_container', ['single_container', 'beat_only_container'])


def volume_fixture(volume, name, scope='function'):
    @pytest.fixture(name=name, scope=scope)
    def fixture(docker_helper):
        volume.set_helper(docker_helper)
        with volume:
            yield volume
    return fixture


static_volume = volume_fixture(VolumeDefinition('static'), 'static_volume')
media_volume = volume_fixture(VolumeDefinition('media'), 'media_volume')
gunicorn_volume = volume_fixture(
    VolumeDefinition('gunicorn'), 'gunicorn_volume')


class NginxContainer(ContainerDefinition):
    def __init__(self, name, image, static_volume, media_volume,
                 gunicorn_volume, **kwargs):
        super().__init__(name, image, **kwargs)
        self._static_volume = static_volume
        self._media_volume = media_volume
        self._gunicorn_volume = gunicorn_volume

    def base_kwargs(self):
        return {
            'ports': {'80/tcp': ('127.0.0.1',)},
            'volumes': {
                self._static_volume.inner(): {
                    'bind': '/usr/share/nginx/static',
                    'mode': 'ro',
                },
                self._media_volume.inner(): {
                    'bind': '/usr/share/nginx/media',
                    'mode': 'ro',
                },
                self._gunicorn_volume.inner(): {
                    'bind': '/var/run/gunicorn',
                    'mode': 'rw',
                },
            }
        }

    def wait_for_start(self):
        # No real way to know when Nginx is ready. Wait a short moment.
        time.sleep(0.5)

    def list_processes(self):
        return list_container_processes(self.inner())

    @classmethod
    def for_fixture(cls, request, name):
        if not request.getfixturevalue('pods'):
            pytest.skip()

        docker_helper = request.getfixturevalue('docker_helper')

        static_volume = request.getfixturevalue('static_volume')
        media_volume = request.getfixturevalue('media_volume')
        gunicorn_volume = request.getfixturevalue('gunicorn_volume')

        return cls(
            name, NGINX_IMAGE, static_volume, media_volume, gunicorn_volume,
            helper=docker_helper)

    @classmethod
    def make_fixture(cls, fixture_name, name, *args, **kw):
        @pytest.fixture(name=fixture_name)
        def fixture(request):
            with cls.for_fixture(request, name, *args, **kw) as container:
                yield container
        return fixture


@pytest.fixture
def nginx_container(request, pods, web_container):
    # FIXME: Find some way for this to not depend on web_container
    if not pods:
        return web_container

    return request.getfixturevalue('nginx_only_container')


nginx_only_container = NginxContainer.make_fixture(
    'nginx_only_container', 'nginx')


__all__ = [
    'amqp_container',
    'beat_container',
    'beat_only_container',
    'db_container',
    'gunicorn_container',
    'gunicorn_volume',
    'media_volume',
    'nginx_container',
    'nginx_only_container',
    'raw_amqp_container',
    'raw_db_container',
    'single_container',
    'static_volume',
    'web_container',
    'web_only_container',
    'worker_container',
    'worker_only_container',
]
