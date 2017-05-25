# mysite
Example Django project for testing. Generated using
```shell
django-admin startproject mysite
```

A `setup.py` was added to install dependencies. An example [Django settings file](mysite/docker_settings.py) was also added to make configuration in a Docker container easier. An example Celery setup (see [`celery.py`](mysite/celery.py)) was added as well.

[django-compressor](https://django-compressor.readthedocs.io) is set up to compress some JavaScript and CSS in a dummy template.

## Usage
A [Docker Compose file](docker-compose.yml) is provided that sets up some infrastructure (RabbitMQ and PostgreSQL instances) for the container to use.

To get started:
```shell
# Pick the Python version to use (defaults to py3)
export VARIANT=py2

# Bring up the infrastructure: PostgreSQL and RabbitMQ
docker-compose up -d db amqp && sleep

# Bring everything else up
docker-compose up
```

To connect to the website, get its address on the host using
```shell
docker-compose port web 8000
```
...and enter that into your browser (you may be more interested in `/admin`).
