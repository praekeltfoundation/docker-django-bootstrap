FROM praekeltfoundation/django-bootstrap:py3
ONBUILD COPY . /app
# chown the app directory after copying in case the copied files include
# subdirectories that will be written to, e.g. the media directory
ONBUILD RUN chown -R django:django /app
ONBUILD RUN pip install -e .
