FROM nginx:stable-alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY config/ /etc/nginx/

VOLUME /usr/share/nginx/static /usr/share/nginx/media /var/run/gunicorn
