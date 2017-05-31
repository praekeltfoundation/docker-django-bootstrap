ARG VARIANT=py3
FROM praekeltfoundation/django-bootstrap:$VARIANT
COPY . /app
RUN pip install -e .
ENV DJANGO_SETTINGS_MODULE mysite.docker_settings
ENV CELERY_APP mysite
RUN django-admin collectstatic --noinput \
    && django-admin compress
CMD ["mysite.wsgi:application"]
