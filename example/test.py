#!/usr/bin/env python3
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import iso8601
import pytest
from testtools.assertions import assert_that
from testtools.matchers import (
    AfterPreprocessing as After, Contains, Equals, GreaterThan, HasLength,
    LessThan, MatchesAll, MatchesAny, MatchesDict, MatchesListwise,
    MatchesRegex, MatchesSetwise, MatchesStructure, Not)

from docker_helper import list_container_processes, output_lines
from fixtures import *  # noqa: We import these so pytest can find them.


# Turn off spam from all the random loggers that set themselves up behind us.
for logger in logging.Logger.manager.loggerDict.values():
    if isinstance(logger, logging.Logger):
        logger.setLevel(logging.WARNING)
# Turn on spam from the loggers we're interested in.
logging.getLogger('docker_helper.helper').setLevel(logging.DEBUG)


def filter_ldconfig_process(ps_rows):
    """
    Sometimes an ldconfig process running under the django user shows up.
    Filter it out.
    :param ps_rows: A list of PsRow objects.
    """
    return [row for row in ps_rows
            if not (row.ruser == 'django' and 'ldconfig' in row.args)]


def assert_tini_pid_1(ps_row, cmd):
    args = 'tini -- django-entrypoint.sh {}'.format(cmd)
    assert_that(ps_row,
                MatchesStructure.byEquality(pid='1', ruser='root', args=args))


def matches_attributes_values(attributes, values):
    """
    Returns a matcher that matches the values of several attributes of an
    object.
    """
    return MatchesStructure.byEquality(
        **{a: v for a, v in zip(attributes, values)})


def matches_ruser_args_unordered(*expected_values):
    """
    Returns a matcher that, given a list of PsRow objects, ensures that objects
    are present that have 'ruser' and 'args' values that match those given.
    """
    def row_matcher(values):
        return matches_attributes_values(['ruser', 'args'], values)

    return MatchesSetwise(*map(row_matcher, expected_values))


def find_prefork_worker_split(ps_rows):
    """
    Given a list of PsRow objects for a group of processes using a pre-fork
    worker process model, finds the row for the "master" process as well as
    a list of "worker" processes.
    """
    ppid_to_rows = {}
    for row in ps_rows:
        ppid_to_rows.setdefault(row.ppid, []).append(row)

    # There should only be two ppids: the parent of the master and the master
    assert len(ppid_to_rows) == 2

    parent_rows = []
    for rows in ppid_to_rows.values():
        for row in rows:
            if row.pid in ppid_to_rows:
                parent_rows.append(row)

    # There should be only one parent among the processes
    assert len(parent_rows) == 1

    [master_row] = parent_rows
    return (master_row, ppid_to_rows[master_row.pid])


class TestWeb(object):
    def test_expected_processes(self, web_only_container):
        """
        When the container is running, there should be 5 running processes:
        tini, the Nginx master and worker, and the Gunicorn master and worker.
        """
        ps_data = filter_ldconfig_process(
            list_container_processes(web_only_container))

        # Sometimes it takes a little while for the processes to settle so try
        # a few times with a delay inbetween.
        retries = 3
        delay = 0.5
        for _ in range(retries):
            if len(ps_data) == 5:
                break
            time.sleep(delay)
            ps_data = filter_ldconfig_process(
                list_container_processes(web_only_container))

        tini = ps_data[0]
        assert_tini_pid_1(tini, 'mysite.wsgi:application')

        gunicorn_rows = [row for row in ps_data if 'gunicorn' in row.args]
        gunicorn_master, gunicorn_workers = (
            find_prefork_worker_split(gunicorn_rows))
        assert_that(gunicorn_master, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            (tini.pid, 'django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117')
        ))

        assert_that(gunicorn_workers, HasLength(1))
        [gunicorn_worker] = gunicorn_workers
        assert_that(gunicorn_worker, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            (gunicorn_master.pid, 'django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117')
        ))

        nginx_rows = [row for row in ps_data if 'nginx' in row.args]
        nginx_master, nginx_workers = find_prefork_worker_split(nginx_rows)
        assert_that(nginx_master, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            # FIXME: Nginx should not be parented by Gunicorn
            (gunicorn_master.pid, 'root',
             'nginx: master process nginx -g daemon off;')
        ))

        assert_that(nginx_workers, HasLength(1))
        [nginx_worker] = nginx_workers
        assert_that(nginx_worker, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            (nginx_master.pid, 'nginx', 'nginx: worker process')
        ))

        # Check that we've inspected all the processes
        assert_that(
            [tini,
             gunicorn_master, gunicorn_worker,
             nginx_master, nginx_worker],
            MatchesSetwise(*map(Equals, ps_data)))

    def test_expected_processes_single_container(self, single_container):
        """
        When the container is running, there should be 7 running processes:
        tini, the Nginx master and worker, the Gunicorn master and worker, and
        the Celery worker ("solo", non-forking) and beat processes.
        """
        ps_data = list_container_processes(single_container)

        tini = ps_data[0]
        assert_tini_pid_1(tini, 'mysite.wsgi:application')

        gunicorn_rows = [row for row in ps_data if 'gunicorn' in row.args]
        gunicorn_master, gunicorn_workers = (
            find_prefork_worker_split(gunicorn_rows))
        assert_that(gunicorn_master, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            (tini.pid, 'django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117')
        ))

        assert_that(gunicorn_workers, HasLength(1))
        [gunicorn_worker] = gunicorn_workers
        assert_that(gunicorn_worker, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            (gunicorn_master.pid, 'django',
             '/usr/local/bin/python /usr/local/bin/gunicorn '
             'mysite.wsgi:application --pid /var/run/gunicorn/gunicorn.pid '
             '--bind unix:/var/run/gunicorn/gunicorn.sock --umask 0117')
        ))

        nginx_rows = [row for row in ps_data if 'nginx' in row.args]
        nginx_master, nginx_workers = find_prefork_worker_split(nginx_rows)
        assert_that(nginx_master, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            # FIXME: Nginx should not be parented by Gunicorn
            (gunicorn_master.pid, 'root',
             'nginx: master process nginx -g daemon off;')
        ))

        assert_that(nginx_workers, HasLength(1))
        [nginx_worker] = nginx_workers
        assert_that(nginx_worker, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            (nginx_master.pid, 'nginx', 'nginx: worker process')
        ))

        celery_worker_rows = [
            row for row in ps_data if 'celery worker' in row.args]
        assert_that(celery_worker_rows, HasLength(1))
        [celery_worker] = celery_worker_rows
        assert_that(celery_worker, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            # FIXME: Celery worker should not be parented by Gunicorn
            (gunicorn_master.pid, 'django',
             '/usr/local/bin/python /usr/local/bin/celery worker --pool=solo '
             '--pidfile worker.pid --concurrency 1')
        ))

        celery_beat_rows = [
            row for row in ps_data if 'celery beat' in row.args]
        assert_that(celery_beat_rows, HasLength(1))
        [celery_beat] = celery_beat_rows
        assert_that(celery_beat, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            # FIXME: Celery beat should not be parented by Gunicorn
            (gunicorn_master.pid, 'django',
             '/usr/local/bin/python /usr/local/bin/celery beat --pidfile '
             'beat.pid')
        ))

        # Check that we've inspected all the processes
        assert_that(
            [tini,
             gunicorn_master, gunicorn_worker,
             nginx_master, nginx_worker,
             celery_worker, celery_beat],
            MatchesSetwise(*map(Equals, ps_data)))

    @pytest.mark.clean_db
    def test_database_tables_created(self, db_container, web_container):
        """
        When the web container is running, a migration should have completed
        and there should be some tables in the database.
        """
        psql_output = db_container.exec_run(
            ['psql', '-qtA', '--dbname', 'mysite', '-c',
             ('SELECT COUNT(*) FROM information_schema.tables WHERE '
              "table_schema='public';")],
            user='postgres').decode('utf-8')

        count = int(psql_output.strip())
        assert_that(count, GreaterThan(0))

    def test_admin_site_live(self, web_client):
        """
        When we get the /admin/ path, we should receive some HTML for the
        Django admin interface.
        """
        response = web_client('/admin/')

        assert_that(response.headers['Content-Type'],
                    Equals('text/html; charset=utf-8'))
        assert_that(response.text,
                    Contains('<title>Log in | Django site admin</title>'))

    def test_nginx_access_logs(self, web_container, web_client):
        """
        When a request has been made to the container, Nginx logs access logs
        to stdout
        """
        # Wait a little bit so that previous tests' requests have been written
        # to the log.
        time.sleep(0.2)
        before_lines = output_lines(
            web_container.logs(stdout=True, stderr=False))

        # Make a request to see the logs for it
        web_client('/')

        # Wait a little bit so that our request has been written to the log.
        time.sleep(0.2)
        after_lines = output_lines(
            web_container.logs(stdout=True, stderr=False))

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

    def test_static_file(self, web_client):
        """
        When a static file is requested, Nginx should serve the file with the
        correct mime type.
        """
        response = web_client('/static/admin/css/base.css')

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.text, Contains('DJANGO Admin styles'))

    def test_manifest_static_storage_file(self, web_container, web_client):
        """
        When a static file that was processed by Django's
        ManifestStaticFilesStorage system is requested, that file should be
        served with a far-future 'Cache-Control' header.
        """
        hashed_svg = web_container.exec_run(
            ['find', 'static/admin/img', '-regextype', 'posix-egrep', '-regex',
             '.*\.[a-f0-9]{12}\.svg$'])
        test_file = output_lines(hashed_svg)[0]

        response = web_client('/' + test_file)

        assert_that(response.headers['Content-Type'], Equals('image/svg+xml'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_django_compressor_js_file(self, web_container, web_client):
        """
        When a static JavaScript file that was processed by django_compressor
        is requested, that file should be served with a far-future
        'Cache-Control' header.
        """
        compressed_js = web_container.exec_run(
            ['find', 'static/CACHE/js', '-name', '*.js'])
        test_file = output_lines(compressed_js)[0]

        response = web_client('/' + test_file)

        assert_that(response.headers['Content-Type'],
                    Equals('application/javascript'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_django_compressor_css_file(self, web_container, web_client):
        """
        When a static CSS file that was processed by django_compressor is
        requested, that file should be served with a far-future 'Cache-Control'
        header.
        """
        compressed_js = web_container.exec_run(
            ['find', 'static/CACHE/css', '-name', '*.css'])
        test_file = output_lines(compressed_js)[0]

        response = web_client('/' + test_file)

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Cache-Control'],
                    Equals('max-age=315360000, public, immutable'))

    def test_gzip_css_compressed(self, web_container, web_client):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should be served gzipped.
        """
        css_to_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '+1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = web_client('/' + test_file,
                              headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Content-Encoding'], Equals('gzip'))
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_woff_not_compressed(self, web_container, web_client):
        """
        When a .woff file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should not be served gzipped as it is already a compressed format.
        """
        woff_to_not_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.woff', '-size', '+1024c'])
        test_file = output_lines(woff_to_not_gzip)[0]

        response = web_client('/' + test_file,
                              headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'],
                    Equals('application/font-woff'))
        assert_that(response.headers, MatchesAll(
            Not(Contains('Content-Encoding')),
            Not(Contains('Vary')),
        ))

    def test_gzip_accept_encoding_respected(self, web_container, web_client):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header does not list gzip as an accepted encoding,
        the file should not be served gzipped, but the 'Vary' header should be
        set to 'Accept-Encoding'.
        """
        css_to_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '+1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = web_client('/' + test_file,
                              headers={'Accept-Encoding': ''})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers, Not(Contains('Content-Encoding')))
        # The Vary header should be set if there is a *possibility* that this
        # file will be served with a different encoding.
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_via_compressed(self, web_container, web_client):
        """
        When a CSS file larger than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding and the
        'Via' header is set, the file should be served gzipped.
        """
        css_to_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '+1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = web_client(
            '/' + test_file,
            headers={'Accept-Encoding': 'gzip', 'Via': 'Internet.org'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers['Content-Encoding'], Equals('gzip'))
        assert_that(response.headers['Vary'], Equals('Accept-Encoding'))

    def test_gzip_small_file_not_compressed(self, web_container, web_client):
        """
        When a CSS file smaller than 1024 bytes is requested and the
        'Accept-Encoding' header lists gzip as an accepted encoding, the file
        should not be served gzipped.
        """
        css_to_gzip = web_container.exec_run(
            ['find', 'static', '-name', '*.css', '-size', '-1024c'])
        test_file = output_lines(css_to_gzip)[0]

        response = web_client('/' + test_file,
                              headers={'Accept-Encoding': 'gzip'})

        assert_that(response.headers['Content-Type'], Equals('text/css'))
        assert_that(response.headers, MatchesAll(
            Not(Contains('Content-Encoding')),
            Not(Contains('Vary')),
        ))


class TestCeleryWorker(object):
    def test_expected_processes(self, worker_only_container):
        """
        When the container is running, there should be 3 running processes:
        tini, and the Celery worker master and worker.
        """
        ps_data = list_container_processes(worker_only_container)

        tini = ps_data[0]
        assert_tini_pid_1(tini, 'celery worker')

        # Filtering the rows here is *slightly* more complicated than elsewhere
        # since the phrase 'celery worker' is also in the tini command
        worker_rows = [
            row for row in ps_data
            if 'celery worker' in row.args and 'tini' not in row.args]
        worker_master, worker_workers = find_prefork_worker_split(worker_rows)
        assert_that(worker_master, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            (tini.pid, 'django',
             '/usr/local/bin/python /usr/local/bin/celery worker '
             '--concurrency 1')
        ))

        assert_that(worker_workers, HasLength(1))
        [worker_worker] = worker_workers
        assert_that(worker_worker, matches_attributes_values(
            ('ppid', 'ruser', 'args'),
            (worker_master.pid, 'django',
             '/usr/local/bin/python /usr/local/bin/celery worker '
             '--concurrency 1')
        ))

        # Check that we've inspected all the processes
        assert_that([tini, worker_master, worker_worker],
                    MatchesSetwise(*map(Equals, ps_data)))

    @pytest.mark.clean_amqp
    def test_amqp_queues_created(self, amqp_container, worker_container):
        """
        When the worker container is running, the three default Celery queues
        should have been created in RabbitMQ.
        """
        rabbitmq_output = amqp_container.exec_run(
            ['rabbitmqctl', '-q', 'list_queues', '-p', '/mysite'])
        rabbitmq_lines = output_lines(rabbitmq_output)
        rabbitmq_data = [line.split(None, 1) for line in rabbitmq_lines]

        assert_that(rabbitmq_data, MatchesSetwise(*map(MatchesListwise, (
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
        ps_data = list_container_processes(beat_only_container)

        assert_that(ps_data, HasLength(2))
        assert_tini_pid_1(ps_data[0], 'celery beat')
        # We don't know what PID we will get, so don't check it
        assert_that(ps_data[1], MatchesStructure.byEquality(
            ruser='django',
            args='/usr/local/bin/python /usr/local/bin/celery beat',
        ))
