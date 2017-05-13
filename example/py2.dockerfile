FROM praekeltfoundation/django-bootstrap:py2-onbuild
ENV DJANGO_SETTINGS_MODULE mysite.docker_settings
ENV CELERY_APP mysite
RUN django-admin collectstatic --noinput
CMD ["mysite.wsgi:application"]
