FROM praekeltfoundation/django-bootstrap:py2-onbuild
ENV DJANGO_SETTINGS_MODULE mysite.settings
RUN django-admin collectstatic --noinput
CMD ["mysite.wsgi:application"]
