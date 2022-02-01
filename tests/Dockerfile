ARG VARIANT=py3-stretch
ARG BASE_IMAGE=praekeltfoundation/django-bootstrap
FROM $BASE_IMAGE:$VARIANT

RUN command -v ps > /dev/null || apt-get-install.sh procps

ARG PROJECT=django2
COPY ${PROJECT} /app/

RUN pip install -e .

ENV DJANGO_SETTINGS_MODULE mysite.docker_settings
ENV CELERY_APP mysite

RUN django-admin collectstatic --noinput \
    && django-admin compress

CMD ["mysite.wsgi:application"]
