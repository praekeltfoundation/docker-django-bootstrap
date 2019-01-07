import os


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


def _prometheus_multiproc_dir():
    # Use the existing value if there is one
    if "prometheus_multiproc_dir" in os.environ:
        return os.environ["prometheus_multiproc_dir"]

    # If the client isn't installed don't set the variable
    try:
        import prometheus_client  # noqa: F401
    except ImportError:
        return None

    # If we got this far we can manage the directory ourselves, hopefully
    default_prometheus_multiproc_dir = "/run/gunicorn/prometheus"

    try:
        os.mkdir(default_prometheus_multiproc_dir)
    except FileExistsError:
        pass

    return default_prometheus_multiproc_dir


prometheus_multiproc_dir = _prometheus_multiproc_dir()
if prometheus_multiproc_dir:
    raw_env = ["prometheus_multiproc_dir=" + prometheus_multiproc_dir]


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
