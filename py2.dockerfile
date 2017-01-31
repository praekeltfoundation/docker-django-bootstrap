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
# Install nginx
RUN apt-get-install.sh libpq5 nginx-extras \
    && adduser www-data gunicorn

# Install nginx-lua-prometheus
# FIXME: No release yet... install from known-good commit
ENV NGINX_LUA_PROMETHEUS_GIT_SHA 0f229261cc45bb1e23c5cb418ad130d183229a7f
RUN set -x \
    && apt-get-install.sh wget \
    && wget -O nginx-lua-prometheus.tar.gz "https://github.com/knyar/nginx-lua-prometheus/archive/$NGINX_LUA_PROMETHEUS_GIT_SHA.tar.gz" \
    && mkdir /nginx-lua-prometheus \
    && tar -xzC /nginx-lua-prometheus --strip-components=1 -f nginx-lua-prometheus.tar.gz \
    && rm nginx-lua-prometheus.tar.gz \
    && apt-get-purge.sh wget

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
