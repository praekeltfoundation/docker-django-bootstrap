FROM praekeltfoundation/python-base:3.6

# Create the user and working directories first as they shouldn't change often.
# Specify the UID/GIDs so that they do not change somehow and mess with the
# ownership of external volumes.
RUN set -ex; \
    addgroup --system --gid 107 django; \
    adduser --system --uid 104 --ingroup django django; \
    \
    mkdir /var/run/gunicorn; \
    chown django:django /var/run/gunicorn; \
    \
    mkdir /var/run/celery; \
    chown django:django /var/run/celery

# Install libpq for psycopg2 for PostgreSQL support
RUN apt-get-install.sh libpq5

# Install a modern Nginx and configure
ENV NGINX_VERSION 1.12.0-1~jessie
RUN apt-key adv --keyserver hkp://pgp.mit.edu:80 --recv-keys 573BFD6B3D8FBC641079A6ABABF5BD827BD9BF62 \
    && echo 'deb http://nginx.org/packages/debian/ jessie nginx' > /etc/apt/sources.list.d/nginx.list \
    && apt-get-install.sh "nginx=$NGINX_VERSION" \
    && rm /etc/nginx/conf.d/default.conf \
# Add nginx user to django group so that Nginx can read/write to gunicorn socket
    && adduser nginx django
COPY nginx/ /etc/nginx/

# Install gunicorn
COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

EXPOSE 8000
WORKDIR /app

COPY django-entrypoint.sh celery-entrypoint.sh \
    /scripts/
ENTRYPOINT ["dinit", "django-entrypoint.sh"]
CMD []
