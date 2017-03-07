FROM praekeltfoundation/django-bootstrap:py3-onbuild
ENV DJANGO_SETTINGS_MODULE mysite.docker_settings
RUN django-admin collectstatic --noinput
CMD ["mysite.wsgi:application"]
