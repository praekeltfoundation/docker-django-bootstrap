ARG VARIANT=py3-stretch
ARG PROJECT=py2
FROM praekeltfoundation/django-bootstrap:$VARIANT
RUN command -v ps > /dev/null || apt-get-install.sh procps
COPY $PROJECT/ /app
RUN pip install -e .
ENV DJANGO_SETTINGS_MODULE mysite.docker_settings
ENV CELERY_APP mysite
RUN django-admin collectstatic --noinput \
    && django-admin compress
CMD ["mysite.wsgi:application"]
