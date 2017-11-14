import os

import pytest


def pytest_addoption(parser):
    parser.addoption(
        '--pods', action='store_true',
        help='run tests for pods')

    parser.addoption(
        '--django-bootstrap-image', action='store',
        default=os.environ.get('DJANGO_BOOTSTRAP_IMAGE', 'mysite:py3'),
        help='django-bootstrap docker image to test')

    parser.addoption(
        '--db-nginx-image', action='store',
        default=os.environ.get(
            'DB_NGINX_IMAGE', 'praekeltfoundation/django-bootstrap:nginx'),
        help='django-bootstrap Nginx docker image to test')


def pytest_report_header(config):
    return 'django-bootstrap docker image: {}, nginx: {}'.format(
        config.getoption('--django-bootstrap-image'),
        config.getoption('--db-nginx-image'))


@pytest.fixture(scope='session')
def pods(request):
    return request.config.getoption('--pods')


@pytest.fixture(scope='session')
def nginx_image(request):
    return request.config.getoption('--db-nginx-image')
