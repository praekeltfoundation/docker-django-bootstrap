import errno
import os

from gunicorn.workers.sync import SyncWorker

# See http://docs.gunicorn.org/en/latest/settings.html for a list of available
# settings. Note that the setting names are used here and not the CLI option
# names (e.g. "pidfile", not "pid").

# Set some sensible Gunicorn options, needed for things to work with Nginx
pidfile = "/run/gunicorn/gunicorn.pid"
bind = "unix:/run/gunicorn/gunicorn.sock"
# umask working files (worker tmp files & unix socket) as 0o117 (i.e. chmod as
# 0o660) so that they are only read/writable by django and nginx users.
umask = 0o117
# Set the worker temporary file directory to /run/gunicorn (rather than default
# of /tmp) so that all of Gunicorn's files are in one place and a tmpfs can be
# mounted at /run for better performance.
# http://docs.gunicorn.org/en/latest/faq.html#blocking-os-fchmod
worker_tmp_dir = "/run/gunicorn"

if os.environ.get("GUNICORN_ACCESS_LOGS"):
    accesslog = "-"


DEFAULT_PROMETHEUS_MULTIPROC_DIR = "/run/gunicorn/prometheus"


def nworkers_changed(server, new_value, old_value):
    # Configure the prometheus_multiproc_dir value. This may seem like a
    # strange place to do that, but it's the only callback that gets called
    # before the WSGI app is setup if app preloading is enabled.

    # We only care about the first time the number of workers is set--during
    # setup. At this point the old_value is None.
    if old_value is not None:
        return

    # If there are multiple processes (num_workers > 1) or the workers are
    # synchronous (in which case in production the num_workers will need to be
    # >1), enable multiprocess mode by default.
    if server.num_workers > 1 or server.worker_class == SyncWorker:
        # Don't override an existing value
        if "prometheus_multiproc_dir" not in os.environ:
            os.environ["prometheus_multiproc_dir"] = (
                DEFAULT_PROMETHEUS_MULTIPROC_DIR)

    if "prometheus_multiproc_dir" in os.environ:
        prometheus_multiproc_dir = os.environ["prometheus_multiproc_dir"]
        try:
            _mkdir_p(prometheus_multiproc_dir)
        except OSError as e:
            server.log.warning(
                "Unable to create prometheus_multiproc_dir directory at '%s'",
                prometheus_multiproc_dir, exc_info=e)


# https://stackoverflow.com/a/600612/3077893
def _mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def worker_exit(server, worker):
    # Do bookkeeping for Prometheus collectors for each worker process as they
    # exit, as described in the prometheus_client documentation:
    # https://github.com/prometheus/client_python#multiprocess-mode-gunicorn
    if "prometheus_multiproc_dir" in os.environ:
        # Don't error if the environment variable has been set but
        # prometheus_client isn't installed
        try:
            from prometheus_client import multiprocess
        except ImportError:
            return

        multiprocess.mark_process_dead(worker.pid)
