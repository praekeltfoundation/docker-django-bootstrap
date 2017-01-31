FROM praekeltfoundation/python-base:debian

# Create the users and working directories first as they shouldn't change often
RUN addgroup --system gunicorn \
    && adduser --system --ingroup gunicorn gunicorn \
    && mkdir /var/run/gunicorn \
    && chown gunicorn:gunicorn /var/run/gunicorn

RUN addgroup --system celery \
    && adduser --system --ingroup celery celery \
    && mkdir /var/run/celery \
    && chown celery:celery /var/run/celery

# Install libpq for psycopg2 for PostgreSQL support
RUN apt-get-install.sh libpq5

# Install a modern Nginx and configure
ENV NGINX_VERSION 1.10.2-1~jessie
RUN apt-key adv --keyserver hkp://pgp.mit.edu:80 --recv-keys 573BFD6B3D8FBC641079A6ABABF5BD827BD9BF62 \
    && echo "deb http://nginx.org/packages/debian/ jessie nginx" >> /etc/apt/sources.list \
    && apt-get-install.sh "nginx=$NGINX_VERSION" \
    && rm /etc/nginx/conf.d/default.conf \
# Add nginx user to gunicorn group so that Nginx can read/write to gunicorn socket
    && adduser nginx gunicorn
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
