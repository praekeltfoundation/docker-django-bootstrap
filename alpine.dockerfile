FROM praekeltfoundation/python-base:alpine
MAINTAINER Praekelt Foundation <dev@praekeltfoundation.org>

# Install libpq for PostgreSQL support and Nginx to serve everything
RUN apk --no-cache add libpq nginx

# Install gunicorn
COPY ./requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

# Copy in the Nginx config
COPY ./nginx/ /etc/nginx/

# Create gunicorn user and group, make directory for socket, and add nginx user
# to gunicorn group so that it can read/write to the socket.
RUN addgroup -S gunicorn \
    && adduser -S -G gunicorn gunicorn \
    && mkdir /var/run/gunicorn \
    && chown gunicorn:gunicorn /var/run/gunicorn \
    && adduser nginx gunicorn

# Create celery user and group, make directory for beat schedule file.
RUN addgroup -S celery \
    && adduser -S -G celery celery \
    && mkdir /var/run/celery \
    && chown celery:celery /var/run/celery

EXPOSE 8000

COPY ./django-entrypoint.sh /scripts/
CMD ["django-entrypoint.sh"]

WORKDIR /app
