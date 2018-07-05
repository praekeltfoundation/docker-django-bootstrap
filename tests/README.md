# Tests
Example Django projects for testing. Generated using
```shell
django-admin startproject mysite
```

Two example projects were set up:
* `py2` with Django 1.11, the final Django version to support Python 2.7.
* `py3` with Django 2+. This should track the latest Django version and work with Python 3 images.

A `setup.py` was added to install dependencies. An example [Django settings file](mysite/docker_settings.py) was also added to make configuration in a Docker container easier. An example Celery setup (see [`celery.py`](mysite/celery.py)) was added as well.

[django-compressor](https://django-compressor.readthedocs.io) is set up to compress some JavaScript and CSS in a dummy template.

## Usage
To build the example site Docker image and run tests on it, use these commands:
```
docker build --tag mysite --build-arg VARIANT=py2-stretch --build-arg PROJECT=py2 .
python test.py mysite
```
