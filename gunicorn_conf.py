import os


# Set some sensible Gunicorn options, needed for things to work with Nginx
pid = "/run/gunicorn/gunicorn.pid"
bind = "unix:/run/gunicorn/gunicorn.sock"
# umask working files (worker tmp files & unix socket) as 0o117 (i.e. chmod as
# 0o660) so that they are only read/writable by django and nginx users.
umask = 0o117

if os.environ.get("GUNICORN_ACCESS_LOGS"):
    access_log_file = "-"
