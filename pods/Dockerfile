ARG PYTHON_VERSION=2.7-jessie
FROM praekeltfoundation/python-base:${PYTHON_VERSION}

# Create the user and working directories first as they shouldn't change often.
# Specify the UID/GIDs so that they do not change somehow and mess with the
# ownership of external volumes.
RUN set -ex; \
    addgroup --system --gid 107 django; \
    adduser --system --uid 104 --ingroup django django; \
    \
    mkdir /var/run/gunicorn /var/run/celery; \
    chown django:django /var/run/gunicorn /var/run/celery

# Install gunicorn
COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

WORKDIR /app

COPY django-entrypoint.sh celery-entrypoint.sh \
    /scripts/
ENTRYPOINT ["tini", "--", "django-entrypoint.sh"]
CMD []
