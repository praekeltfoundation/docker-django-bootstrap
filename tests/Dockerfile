ARG BASE_IMAGE=praekeltfoundation/django-bootstrap:py3-stretch
FROM $BASE_IMAGE

RUN command -v ps > /dev/null || apt-get-install.sh procps

ARG PROJECT=django2
COPY ${PROJECT} /app/

RUN pip install -e .

ENV DJANGO_SETTINGS_MODULE mysite.docker_settings
ENV CELERY_APP mysite

RUN django-admin collectstatic --noinput \
    && django-admin compress

CMD ["mysite.wsgi:application"]
