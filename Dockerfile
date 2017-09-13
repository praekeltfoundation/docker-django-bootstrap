ARG PYTHON_VERSION=2.7
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

# Install libpq for psycopg2 for PostgreSQL support
RUN apt-get-install.sh libpq5

# Install a modern Nginx and configure
ENV OPENRESTY_VERSION 1.11.2.5-1~jessie1
RUN set -ex; \
    apt-key adv --keyserver ha.pool.sks-keyservers.net --recv-keys E52218E7087897DC6DEA6D6D97DB7443D5EDEB74; \
    echo 'deb http://openresty.org/package/debian jessie openresty' > /etc/apt/sources.list.d/openresty.list; \
    \
    apt-get-install.sh "openresty=$OPENRESTY_VERSION"; \
    adduser www-data django
ENV PATH /usr/local/openresty/bin:$PATH
COPY nginx/ /usr/local/openresty/nginx/conf/

# Install gunicorn
COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

EXPOSE 8000
WORKDIR /app

COPY django-entrypoint.sh celery-entrypoint.sh \
    /scripts/
ENTRYPOINT ["tini", "--", "django-entrypoint.sh"]
CMD []
