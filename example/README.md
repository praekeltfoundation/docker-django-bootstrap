# mysite
Example Django project for testing. Generated using
```shell
django-admin startproject mysite
```

A `setup.py` was added to install dependencies. An example [Django settings file](mysite/docker_settings.py) was also added to make configuration in a Docker container easier. An example Celery setup (see [`celery.py`](mysite/celery.py)) was added as well.

[django-compressor](https://django-compressor.readthedocs.io) is set up to compress some JavaScript and CSS in a dummy template.

## Usage
To build the example site Docker image and run tests on it, use these commands:
```
docker build --tag mysite .
python test.py mysite
```
