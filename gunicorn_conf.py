import os

from gunicorn.workers.sync import SyncWorker


def post_fork(server, worker):
    # Since setting the prometheus_multiproc_dir environment variable can make
    # the prometheus_client library create a bunch of files before we want it
    # to, only do so at the very last moment: when we're running a worker.
    # Also check that this is a synchronous worker before doing anything, and
    # don't override an existing value.
    if isinstance(worker, SyncWorker):
        if "prometheus_multiproc_dir" not in os.environ:
            os.environ["prometheus_multiproc_dir"] = "/run/gunicorn/prometheus"


def worker_exit(server, worker):
    # Do the Prometheus multiprocess thing if its working directory is set and
    # the library is importable.
    # https://github.com/prometheus/client_python#multiprocess-mode-gunicorn
    if os.environ.get("prometheus_multiproc_dir"):
        try:
            from prometheus_client import multiprocess
        except ImportError:
            return

        multiprocess.mark_process_dead(worker.pid)
