#!/usr/bin/env python3
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import iso8601

from prometheus_client import parser as prom_parser

import pytest

from seaworthy.ps import build_process_tree
from seaworthy.stream.matchers import OrderedMatcher, RegexMatcher
from seaworthy.testtools import MatchesPsTree
from seaworthy.utils import output_lines

from testtools.assertions import assert_that
from testtools.matchers import (
    AfterPreprocessing as After, Contains, Equals, GreaterThan, HasLength,
    LessThan, MatchesAll, MatchesAny, MatchesDict, MatchesListwise,
    MatchesRegex, MatchesSetwise, Not, StartsWith)

from definitions import (  # noqa: I100,I101
    # dependencies
    amqp_container, db_container,
    # our definitions
    beat_container, single_container, web_container, worker_container,
    # helper function
    make_combined_fixture)


# Turn off spam from all the random loggers that set themselves up behind us.
for logger in logging.Logger.manager.loggerDict.values():
    if isinstance(logger, logging.Logger):
        logger.setLevel(logging.WARNING)
# Turn on spam from the loggers we're interested in.
logging.getLogger('docker_helper.helper').setLevel(logging.DEBUG)


# Set up fixtures. The fixtures are identified by the names passed into the
# factory functions, but we need references to them at module level so pytest
# can find them.
single_container_fixture = single_container.pytest_fixture('single_container')
web_only_fixture = web_container.pytest_fixture('web_only_container')
worker_only_fixture = worker_container.pytest_fixture('worker_only_container')
beat_only_fixture = beat_container.pytest_fixture('beat_only_container')

web_fixture = make_combined_fixture('web')
worker_fixture = make_combined_fixture('worker')
beat_fixture = make_combined_fixture('beat')

raw_db_fixture, db_fixture = db_container.pytest_clean_fixtures(
    'db_container', scope='module')
raw_amqp_fixture, amqp_fixture = amqp_container.pytest_clean_fixtures(
    'amqp_container', scope='module')


def public_tables(db_container):
    return [r[1] for r in db_container.list_tables() if r[0] == 'public']


def filter_ldconfig_process(ps_rows):
    """
    Sometimes an ldconfig process running under the django user shows up.
    Filter it out.
    :param ps_rows: A list of PsRow objects.
    """
    return [row for row in ps_rows
            if not (row.ruser == 'django' and 'ldconfig' in row.args)]


def http_requests_total_for_view(metrics_text, view):
    """
    Get the samples available for a view given the response text from the
    metrics endpoint.
    """
    # https://github.com/prometheus/client_python/#parser
    samples = []
    for family in prom_parser.text_string_to_metric_families(metrics_text):
        if family.name == (
                'django_http_requests_total_by_view_transport_method'):
            for sample in family.samples:
                if sample.labels['view'] == view:
                    samples.append(sample)
            break

    return samples


class TestWeb(object):
    def test_expected_processes(self, web_only_container):
        """
        When the container is running, there should be 5 running processes:
        tini, the Nginx master and worker, and the Gunicorn master and worker.
        """
        ps_rows = filter_ldconfig_process(web_only_container.list_processes())

        # Sometimes it takes a little while for the processes to settle so try
        # a few times with a delay inbetween.
        retries = 3
        delay = 0.5
        for _ in range(retries):
            if len(ps_rows) == 5:
                break
            time.sleep(delay)
            ps_rows = filter_ldconfig_process(
                web_only_container.list_processes())

        ps_tree = build_process_tree(ps_rows)

        tini_args = 'tini -- django-entrypoint.sh mysite.wsgi:application'
        gunicorn_master_args = (
            '/usr/local/bin/python /usr/local/bin/gunicorn '
            'mysite.wsgi:application --config /etc/gunicorn/config.py')
        gunicorn_worker_args = (
            '/usr/local/bin/python /usr/local/bin/gunicorn '
            'mysite.wsgi:application --config /etc/gunicorn/config.py')
        nginx_master_args = 'nginx: master process nginx -g daemon off;'
        nginx_worker_args = 'nginx: worker process'

        assert_that(
            ps_tree,
            MatchesPsTree('root', tini_args, pid=1, children=[
                MatchesPsTree('django', gunicorn_master_args, children=[
                    MatchesPsTree('django', gunicorn_worker_args),
                    # FIXME: Nginx should not be parented by Gunicorn
                    MatchesPsTree('root', nginx_master_args, children=[
                        MatchesPsTree('nginx', nginx_worker_args),
                    ]),
                ]),
            ]))

    def test_expected_processes_single_container(self, single_container):
        """
        When the container is running, there should be 7 running processes:
        tini, the Nginx master and worker, the Gunicorn master and worker, and
        the Celery worker ("solo", non-forking) and beat processes.
        """
        ps_rows = single_container.list_processes()
        ps_tree = build_process_tree(ps_rows)

        tini_args = 'tini -- django-entrypoint.sh mysite.wsgi:application'
        gunicorn_master_args = (
            '/usr/local/bin/python /usr/local/bin/gunicorn '
            'mysite.wsgi:application --config /etc/gunicorn/config.py')
        gunicorn_worker_args = (
            '/usr/local/bin/python /usr/local/bin/gunicorn '
            'mysite.wsgi:application --config /etc/gunicorn/config.py')
        nginx_master_args = 'nginx: master process nginx -g daemon off;'
        nginx_worker_args = 'nginx: worker process'
        celery_worker_args = (
            '/usr/local/bin/python /usr/local/bin/celery worker --pool=solo '
            '--pidfile worker.pid --concurrency 1')
        celery_beat_args = (
            '/usr/local/bin/python /usr/local/bin/celery beat --pidfile '
            'beat.pid')

        assert_that(
            ps_tree,
            MatchesPsTree('root', tini_args, pid=1, children=[
                MatchesPsTree('django', gunicorn_master_args, children=[
                    MatchesPsTree('django', gunicorn_worker_args),
                    # FIXME: Celery worker should not be parented by Gunicorn
                    MatchesPsTree('django', celery_worker_args),
                    # FIXME: Celery beat should not be parented by Gunicorn
                    MatchesPsTree('django', celery_beat_args),
                    # FIXME: Nginx should not be parented by Gunicorn
                    MatchesPsTree('root', nginx_master_args, children=[
                        MatchesPsTree('nginx', nginx_worker_args),
                    ]),
                ]),
            ]))

    def test_expected_files(self, web_only_container):
        """
        When the container is running, there should be PID files for Nginx and
        Gunicorn, a working directory for Gunicorn, and Gunicorn's Unix socket
        file.
        """
        stat = web_only_container.exec_stat(
            '/run/nginx.pid',
            '/run/gunicorn',
            '/run/gunicorn/gunicorn.sock',
            '/run/gunicorn/gunicorn.pid',
            '/run/gunicorn/prometheus',
        )

        assert_that(stat, Equals([
            '644 root:root',
            '755 django:django',
            '660 django:django',
            '644 django:django',
            '755 django:django',
        ]))

        self._assert_gunicorn_worker_tmp_file(web_only_container)

        self._assert_prometheus_dbs(web_only_container)

    def test_expected_files_single_container(self, single_container):
        """
        When the container is running, there should be PID files for Nginx,
        Gunicorn, and Celery, working directories for Gunicorn and Celery, and
        Gunicorn's Unix socket file.
        """
        stat = single_container.exec_stat(
            '/run/nginx.pid',
            '/run/gunicorn',
            '/run/gunicorn/gunicorn.sock',
            '/run/gunicorn/gunicorn.pid',
            '/run/gunicorn/prometheus',
            '/run/celery',
            '/run/celery/worker.pid',
            '/run/celery/beat.pid',
        )

        assert_that(stat, Equals([
            '644 root:root',
            '755 django:django',
            '660 django:django',
            '644 django:django',
            '755 django:django',
            '755 django:django',
            '644 django:django',
            '644 django:django',
        ]))

        self._assert_gunicorn_worker_tmp_file(single_container)

        self._assert_prometheus_dbs(single_container)

    def _assert_gunicorn_worker_tmp_file(self, container):
        # Find the worker temporary file...this is quite involved because it's
        # a temp file without a predictable name and Gunicorn unlinks it so we
        # can't just stat it
        ps_rows = container.list_processes()
        gunicorns = [r for r in ps_rows if '/usr/local/bin/gunicorn' in r.args]
        worker = gunicorns[-1]  # Already sorted by PID, pick the highest PID
        proc_fd_path = '/proc/{}/fd'.format(worker.pid)

        # Due to container restrictions, the root user doesn't have access to
        # /proc/pid/fd/*--we must run as the django user.
        fd_targets = container.exec_run([
            'bash', '-c',
            'for fd in {}/*; do readlink -f "$fd"; done'.format(proc_fd_path)
        ], user='django')

        # Filter out pipes and sockets
        pipe_path = '{}/pipe'.format(proc_fd_path)
        ceci_nest_pas_une_pipe = (
            [t for t in fd_targets if not t.startswith(pipe_path)])
        sock_path = '{}/socket'.format(proc_fd_path)
        neither_pipes_nor_socks = (
            [t for t in ceci_nest_pas_une_pipe if not t.startswith(sock_path)])

        # Sometimes things like /dev/urandom are in there too
        files = (
            [t for t in neither_pipes_nor_socks if not t.startswith('/dev/')])
        not_prom_files = (
            [t for t in files if not t.startswith('/run/gunicorn/prometheus/')]
        )

        # Finally, assert the worker temp file is in the place we expect
        assert_that(not_prom_files, MatchesListwise([
            StartsWith('/run/gunicorn/wgunicorn-')
        ]))

    def _assert_prometheus_dbs(self, container):
        # The worker Gunicorn process has some process-specific db-files. Get
        # the PID and assert there are files for it.
        ps_rows = container.list_processes()
        gunicorns = [r for r in ps_rows if '/usr/local/bin/gunicorn' in r.args]
        pid = gunicorns[-1].pid  # Already sorted by PID, pick the highest PID

        prom_files = container.exec_find(
            ['/run/gunicorn/prometheus/', '-type', 'f'])
        assert_that(prom_files, MatchesSetwise(
            Equals('/run/gunicorn/prometheus/counter_{}.db'.format(pid)),
            Equals('/run/gunicorn/prometheus/gauge_all_{}.db'.format(pid)),
            Equals('/run/gunicorn/prometheus/histogram_{}.db'.format(pid)),
        ))

    @pytest.mark.clean_db_container
    def test_database_tables_created(self, db_container, web_container):
        """
        When the web container is running, a migration should have completed
        and there should be some tables in the database.
        """
        assert_that(len(public_tables(db_container)), GreaterThan(0))

    @pytest.mark.clean_db_container
    def test_database_tables_not_created(self, docker_helper, db_container):
        """
        When the web container is running with the `SKIP_MIGRATIONS`
        environment variable set, there should be no tables in the database.
        """
        self._test_database_tables_not_created(
            docker_helper, db_container, web_container)

    @pytest.mark.clean_db_container
    def test_database_tables_not_created_single(
            self, docker_helper, db_container, amqp_container):
        """
        When the single container is running with the `SKIP_MIGRATIONS`
        environment variable set, there should be no tables in the database.
        """
        self._test_database_tables_not_created(
            docker_helper, db_container, single_container)

    def _test_database_tables_not_created(
            self, docker_helper, db_container, django_container):
        assert_that(public_tables(db_container), Equals([]))

        django_container.set_helper(docker_helper)
        with django_container.setup(environment={'SKIP_MIGRATIONS': '1'}):
            if django_container.django_maj_version() >= 2:
                assert_that(public_tables(db_container), Equals([]))
            else:
                # On Django 1, if our app has any models (and the
                # django-prometheus package adds one), then an empty table
                # called "django_migrations" is created, even if migrations
                # aren't run.
                assert_that(
                    public_tables(db_container), Equals(['django_migrations']))
                [count] = output_lines(db_container.exec_psql(
                    'SELECT COUNT(*) FROM django_migrations;'))
                assert_that(int(count), Equals(0))

    def test_admin_site_live(self, web_container):
        """
        When we get the /admin/ path, we should receive some HTML for the
        Django admin interface.
        """
        web_client = web_container.http_client()
        response = web_client.get('/admin/')

        assert_that(response.headers['Content-Type'],
                    Equals('text/html; charset=utf-8'))
        assert_that(response.text,
                    Contains('<title>Log in | Django site admin</title>'))

    def test_prometheus_metrics_live(self, web_container):
        """
        When we get the /metrics path, we should receive Prometheus metrics.
        """
        web_client = web_container.http_client()
        response = web_client.get('/metrics')

        assert_that(response.headers['Content-Type'],
                    Equals('text/plain; version=0.0.4; charset=utf-8'))

        [sample] = http_requests_total_for_view(
            response.text, 'prometheus-django-metrics')
        assert_that(sample.labels['transport'], Equals('http'))
        assert_that(sample.labels['method'], Equals('GET'))
        assert_that(sample.value, Equals(1.0))

    def test_prometheus_metrics_worker_restart(self, web_container):
        """
        When a worker process is restarted, Prometheus counters should be
        preserved, such that a call to the metrics endpoint before a worker
        restart can be observed after the worker restart.
        """
        web_client = web_container.http_client()
        response = web_client.get('/metrics', headers={'Connection': 'close'})

        [sample] = http_requests_total_for_view(
            response.text, 'prometheus-django-metrics')
        assert_that(sample.value, Equals(1.0))
        response.close()

        # Signal Gunicorn so that it restarts the worker(s)
        # http://docs.gunicorn.org/en/latest/signals.html
        web_container.inner().kill("SIGHUP")

        matcher = OrderedMatcher(*(RegexMatcher(r) for r in (
            r'Booting worker',  # Original worker start on startup
            r'Booting worker',  # Worker start after SIGHUP restart
        )))
        web_container.wait_for_logs_matching(
            matcher, web_container.wait_timeout)

        # Now try make another request and ensure the counter was incremented
        response = web_client.get('/metrics')
        [sample] = http_requests_total_for_view(
            response.text, 'prometheus-django-metrics')
        assert_that(sample.value, Equals(2.0))

    def test_prometheus_metrics_web_concurrency(
            self, docker_helper, db_container):
        """
        When the web container is running with multiple worker processes,
        multiple requests to the admin or metrics endpoints should result in
        the expected metrics.
        """
        self._test_prometheus_metrics_web_concurrency(
            docker_helper, web_container)

    def test_prometheus_metrics_web_concurrency_single(
            self, docker_helper, db_container, amqp_container):
        """
        When the single container is running with multiple worker processes,
        multiple requests to the admin or metrics endpoints should result in
        the expected metrics.
        """
        self._test_prometheus_metrics_web_concurrency(
            docker_helper, single_container)

    def _test_prometheus_metrics_web_concurrency(
            self, docker_helper, django_container):
        django_container.set_helper(docker_helper)

        # Mo' workers mo' problems
        # FIXME: Make this a bit less hacky somehow...
        django_container.wait_matchers *= 4

        with django_container.setup(environment={'WEB_CONCURRENCY': '4'}):
            client = django_container.http_client()

            # Make a bunch of requests
            for _ in range(10):
                response = client.get('/admin')
                assert_that(response.status_code, Equals(200))

            # Check the metrics a bunch of times for a few things...
            # We don't know which worker serves which request, so we just
            # make a few requests hoping we'll hit multiple/all of them.
            for i in range(10):
                response = client.get('/metrics')

                # Requests to the admin page are counted
                [admin_sample] = http_requests_total_for_view(
                    response.text, view='admin:index')
                assert_that(admin_sample.value, Equals(10.0))

                # Requests to the metrics endpoint increment
                [metrics_sample] = http_requests_total_for_view(
                    response.text, 'prometheus-django-metrics')
                assert_that(metrics_sample.value, Equals(i + 1))

                # django_migrations_ samples are per-process, with a pid label.
                # Check that there are 4 different pids.
                fs = prom_parser.text_string_to_metric_families(response.text)
                [family] = [f for f in fs
                            if f.name == 'django_migrations_applied_total']
                pids = set()
                for sample in family.samples:
                    pids.add(sample.labels['pid'])
                assert_that(pids, HasLength(4))

    def test_nginx_access_logs(self, web_container):
        """
        When a request has been made to the container, Nginx logs access logs
        to stdout
        """
        # Wait a little bit so that previous tests' requests have been written
        # to the log.
        time.sleep(0.2)
        before_lines = output_lines(web_container.get_logs(stderr=False))

        # Make a request to see the logs for it
        web_client = web_container.http_client()
        web_client.get('/')

        # Wait a little bit so that our request has been written to the log.
        time.sleep(0.2)
        after_lines = output_lines(web_container.get_logs(stderr=False))

        new_lines = after_lines[len(before_lines):]
        assert_that(len(new_lines), GreaterThan(0))

        # Find the Nginx log line
        nginx_lines = [l for l in new_lines if re.match(r'^\{ "time": .+', l)]
        assert_that(nginx_lines, HasLength(1))

        now = datetime.now(timezone.utc)
        assert_that(json.loads(nginx_lines[0]), MatchesDict({
            # Assert time is valid and recent
            'time': After(iso8601.parse_date, MatchesAll(
                MatchesAny(LessThan(now), Equals(now)),
                MatchesAny(GreaterThan(now - timedelta(seconds=5)))
            )),

            'request': Equals('GET / HTTP/1.1'),
            'status': Equals(404),
            'body_bytes_sent': GreaterThan(0),
            'request_time': LessThan(1.0),
            'http_referer': Equals(''),

            # Assert remote_addr is an IPv4 (roughly)
            'remote_addr': MatchesRegex(
                r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'),
            'http_host': MatchesRegex(r'^127.0.0.1:\d{4,5}$'),
            'http_user_agent': MatchesRegex(r'^python-requests/'),

            # Not very interesting empty fields
            'remote_user': Equals(''),
            'http_via': Equals(''),
            'http_x_forwarded_proto': Equals(''),
            'http_x_forwarded_for': Equals(''),
        }))

    def test_gunicorn_access_logs(self, docker_helper, db_container):
        """
        When the web container is running with the `GUNICORN_ACCESS_LOGS`
        environment variable set, Gunicorn access logs should be output.
        """
        self._test_gunicorn_access_logs(docker_helper, web_container)

    def test_gunicorn_access_logs_single(
            self, docker_helper, db_container, amqp_container):
        """
        When the single container is running with the `GUNICORN_ACCESS_LOGS`
        environment variable set, Gunicorn access logs should be output.
        """
        self._test_gunicorn_access_logs(docker_helper, single_container)

    def _test_gunicorn_access_logs(self, docker_helper, web_container):
        web_container.set_helper(docker_helper)
        with web_container.setup(environment={'GUNICORN_ACCESS_LOGS': '1'}):
            # Wait a little bit so that previous tests' requests have been
            # written to the log.
            time.sleep(0.2)
            before_lines = output_lines(web_container.get_logs(stderr=False))

            # Make a request to see the logs for it
            web_client = web_container.http_client()
            web_client.get('/')

            # Wait a little bit so that our request has been written to the log.
            time.sleep(0.2)
            after_lines = output_lines(web_container.get_logs(stderr=False))

            new_lines = after_lines[len(before_lines):]
            assert_that(len(new_lines), GreaterThan(0))

            # Find the Gunicorn log line (the not-Nginx-JSON line)
            gunicorn_lines = [
                l for l in new_lines if not re.match(r'^\{ .+', l)]
            assert_that(gunicorn_lines, HasLength(1))
            assert_that(gunicorn_lines[0], Contains('"GET / HTTP/1.0"'))

    def test_static_file(self, web_container):
        """
        When a static file is requested, Nginx should serve the file with the
        correct mime type.
        """
        web_client = web_container.http_client()
        response = web_client.get('/static/admin/css/base.css')

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.text, Contains('DJANGO Admin styles'))

    def test_manifest_static_storage_file(self, web_container):
        """
        When a static file that was processed by Django's
        ManifestStaticFilesStorage system is requested, that file should be
        served with a far-future 'Cache-Control' header.
        """
        hashed_svg = web_container.exec_find(
            ['static/admin/img', '-regextype', 'posix-egrep', '-regex',
             r'.*\.[a-f0-9]{12}\.svg$'])
        test_file = hashed_svg[0]

        web_client = web_container.http_client()
        response = web_client.get('/' + test_file)

        assert_that(response.headers['Content-Type'], Equals('image/svg+xml'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_django_compressor_js_file(self, web_container):
        """
        When a static JavaScript file that was processed by django_compressor
        is requested, that file should be served with a far-future
        'Cache-Control' header.
        """
        compressed_js = web_container.exec_find(
            ['static/CACHE/js', '-name', '*.js'])
        test_file = compressed_js[0]

        web_client = web_container.http_client()
        response = web_client.get('/' + test_file)

        assert_that(response.headers['Content-Type'],
                    Equals('application/javascript'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_django_compressor_css_file(self, web_container):
        """
        When a static CSS file that was processed by django_compressor is
        requested, that file should be served with a far-future 'Cache-Control'
        header.
        """
        compressed_js = web_container.exec_find(
            ['static/CACHE/css', '-name', '*.css'])
        test_file = compressed_js[0]

        web_client = web_container.http_client()
        response = web_client.get('/' + test_file)

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_gzip_css_compressed(self, web_container):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should be served gzipped.
        """
        css_to_gzip = web_container.exec_find(
            ['static', '-name', '*.css', '-size', '+1024c'])
        test_file = css_to_gzip[0]

        web_client = web_container.http_client()
        response = web_client.get(
            '/' + test_file, headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Content-Encoding'], Equals('gzip'))
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_woff_not_compressed(self, web_container):
        """
        When a .woff file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should not be served gzipped as it is already a compressed format.
        """
        woff_to_not_gzip = web_container.exec_find(
            ['static', '-name', '*.woff', '-size', '+1024c'])
        test_file = woff_to_not_gzip[0]

        web_client = web_container.http_client()
        response = web_client.get(
            '/' + test_file, headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'],
                    Equals('application/font-woff'))
        assert_that(response.headers, MatchesAll(
            Not(Contains('Content-Encoding')),
            Not(Contains('Vary')),
        ))

    def test_gzip_accept_encoding_respected(self, web_container):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header does not list gzip as an accepted encoding,
        the file should not be served gzipped, but the 'Vary' header should be
        set to 'Accept-Encoding'.
        """
        css_to_gzip = web_container.exec_find(
            ['static', '-name', '*.css', '-size', '+1024c'])
        test_file = css_to_gzip[0]

        web_client = web_container.http_client()
        response = web_client.get(
            '/' + test_file, headers={'Accept-Encoding': ''})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers, Not(Contains('Content-Encoding')))
        # The Vary header should be set if there is a *possibility* that this
        # file will be served with a different encoding.
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_via_compressed(self, web_container):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding and the
        'Via' header is set, the file should be served gzipped.
        """
        css_to_gzip = web_container.exec_find(
            ['static', '-name', '*.css', '-size', '+1024c'])
        test_file = css_to_gzip[0]

        web_client = web_container.http_client()
        response = web_client.get(
            '/' + test_file,
            headers={'Accept-Encoding': 'gzip', 'Via': 'Internet.org'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Content-Encoding'], Equals('gzip'))
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_small_file_not_compressed(self, web_container):
        """
        When a CSS file smaller than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should not be served gzipped.
        """
        css_to_gzip = web_container.exec_find(
            ['static', '-name', '*.css', '-size', '-1024c'])
        test_file = css_to_gzip[0]

        web_client = web_container.http_client()
        response = web_client.get(
            '/' + test_file, headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers, MatchesAll(
            Not(Contains('Content-Encoding')),
            Not(Contains('Vary')),
        ))

    def test_media_volume_ownership(self, web_container):
        """
        The /app/media directory should have the correct ownership set at
        runtime if it is a mounted volume.
        """
        [app_media_ownership] = web_container.exec_run(
            ['stat', '-c', '%U:%G', '/app/media'])

        assert_that(app_media_ownership, Equals('django:django'))


class TestCeleryWorker(object):
    def test_expected_processes(self, worker_only_container):
        """
        When the container is running, there should be 3 running processes:
        tini, and the Celery worker master and worker.
        """
        ps_rows = worker_only_container.list_processes()
        ps_tree = build_process_tree(ps_rows)

        tini_args = 'tini -- django-entrypoint.sh celery worker'
        celery_master_args = (
            '/usr/local/bin/python /usr/local/bin/celery worker '
            '--concurrency 1')
        celery_worker_args = (
            '/usr/local/bin/python /usr/local/bin/celery worker '
            '--concurrency 1')

        assert_that(
            ps_tree,
            MatchesPsTree('root', tini_args, pid=1, children=[
                MatchesPsTree('django', celery_master_args, children=[
                    MatchesPsTree('django', celery_worker_args),
                ]),
            ]))

    @pytest.mark.clean_amqp
    def test_amqp_queues_created(self, amqp_container, worker_container):
        """
        When the worker container is running, the three default Celery queues
        should have been created in RabbitMQ.
        """
        queue_data = amqp_container.list_queues()

        assert_that(queue_data, MatchesSetwise(*map(MatchesListwise, (
            [Equals('celery'), Equals('0')],
            [MatchesRegex(r'^celeryev\..+'), Equals('0')],
            [MatchesRegex(r'^celery@.+\.celery\.pidbox$'), Equals('0')],
        ))))


class TestCeleryBeat(object):
    def test_expected_processes(self, beat_only_container):
        """
        When the container is running, there should be 2 running processes:
        tini, and the Celery beat process.
        """
        ps_rows = beat_only_container.list_processes()
        ps_tree = build_process_tree(ps_rows)

        tini_args = 'tini -- django-entrypoint.sh celery beat'
        celery_beat_args = '/usr/local/bin/python /usr/local/bin/celery beat'

        assert_that(
            ps_tree,
            MatchesPsTree('root', tini_args, pid=1, children=[
                MatchesPsTree('django', celery_beat_args),
            ]))
