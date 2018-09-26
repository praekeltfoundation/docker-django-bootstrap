# Tests
Example Django projects for testing. Generated using
```shell
django-admin startproject mysite
```

Two example projects were set up:
* `django1` with Django 1.11, the final Django version to support Python 2.7.
* `django2` with Django 2+. This should track the latest Django version and work with Python 3 images.

A `setup.py` was added to install dependencies. An example [Django settings file](mysite/docker_settings.py) was also added to make configuration in a Docker container easier. An example Celery setup (see [`celery.py`](mysite/celery.py)) was added as well.

[django-compressor](https://django-compressor.readthedocs.io) is set up to compress some JavaScript and CSS in a dummy template.

## Usage
To build the example site Docker image and run tests on it, use commands like this:
```
docker build --tag mysite --build-arg VARIANT=py2-stretch --build-arg PROJECT=django1 .
pytest test.py --django-bootstrap-image=mysite
```
