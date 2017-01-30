# docker-django-bootstrap
Dockerfile for quickly running Django projects in a Docker container.

Run [Django](https://www.djangoproject.com) projects from source using [Gunicorn](http://gunicorn.org) and [Nginx](http://nginx.org).

> **Note**: The tags for these images have changed recently. We've dropped support for Alpine Linux and going forward all images will be Debian-based. In addition, we've added Python 3 support. Whereas before there were `:debian` and `:alpine` tags there are now `:py2` and `:py3` Debian-based tags. The default tags (`:latest` and `:onbuild`) will remain Debian/Python 2-based as they have always been.

## Usage
#### Step 0: Get your Django project in shape
There are a few ways that your Django project needs to be set up in order to be compatible with this Docker image.

**setup.py**  
Your project must have a `setup.py`. All dependencies (including Django itself) need to be listed as `install_requires`.

**Static files**  
Your project's [static files](https://docs.djangoproject.com/en/1.9/howto/static-files/) must be set up as follows:
* `STATIC_URL = '/static/'`
* `STATIC_ROOT` = `BASE_DIR/static` or `BASE_DIR/staticfiles`

**Media files**  
If your project makes use of user-uploaded media files, it must be set up as follows:
* `MEDIA_URL = '/media/'`
* `MEDIA_ROOT` = `BASE_DIR/media` or `BASE_DIR/mediafiles`

***Note:*** Any files stored in directories called `static`, `staticfiles`, `media`, or `mediafiles` in the project root directory will be served by Nginx. Do not store anything here that you do not want the world to see.

#### Step 1: Write a Dockerfile
In the root of the repo for your Django project, add a Dockerfile for the project. For example, this file could contain:
```dockerfile
FROM praekeltfoundation/django-bootstrap:onbuild
ENV DJANGO_SETTINGS_MODULE my_django_project.settings
RUN django-admin collectstatic --noinput
CMD ["my_django_project.wsgi:application"]
```

Let's go through these lines one-by-one:
 1. The `FROM` instruction here tells us which image to base this image on. We use the `django-bootstrap:onbuild` base image.
 2. We set the `DJANGO_SETTINGS_MODULE` environment variable so that Django knows where to find its settings. This is necessary for any `django-admin` commands to work.
 3. *Optional:* If you need to run any build-time tasks, such as collecting static assets, now's the time to do that.
 4. We set the container command (`CMD`) to a list of arguments that will be passed to `gunicorn`. We need to provide Gunicorn with the [`APP_MODULE`](http://docs.gunicorn.org/en/stable/run.html?highlight=app_module#gunicorn), so that it knows which WSGI app to run.*

\*Note that previously the way to do this was to set the `APP_MODULE` environment variable. That still works, but is no longer the recommended way and is deprecated.

The `django-bootstrap:onbuild` base image does a few steps automatically using Docker's `ONBUILD` instruction. It will:
 1. `COPY . /app` - copies the source of your project into the image
 2. `RUN chown -R gunicorn:gunicorn /app` - ensures the `gunicorn` user can write to `/app` and its subdirectories
 3. `RUN pip install -e .` - installs your project using `pip`
All these instructions occur directly after the `FROM` instruction in your Dockerfile. Running these `ONBUILD` steps is *optional*. If you don't want them, you can use the plain `praekeltfoundation/django-bootstrap` image.

By default, the [`django-entrypoint.sh`](django-entrypoint.sh) script is run when the container is started. This script runs a once-off `django-admin migrate` to update the database schemas and then launches `nginx` and `gunicorn` to run the application.

The script also allows you to create a Django super user account if needed. Setting the `SUPERUSER_PASSWORD` environment variable will result in a Django superuser account being made with the `admin` username. This will only happen if no `admin` user exists.

#### Step 2: Add a `.dockerignore` file (if using the `:onbuild` image)
Add a file called `.dockerignore` to the root of your project. A good start is just to copy in the [`.dockerignore` file](example/.dockerignore) from the example Django project in this repo.

The `:onbuild` image automatically copies in the entire source of your project, but some of those files probably *aren't* needed inside the Docker image you're building. We tell Docker about those unneeded files using a `.dockerignore` file, much like how one would tell Git not to track files using a `.gitignore` file.

As a general rule, you should list all the files in your `.gitignore` in your `.dockerignore` file. If you don't need it in Git, you shouldn't need it in Docker.

Additionally, you shouldn't need any *Git* stuff inside your Docker image. It's especially important to have Docker ignore the `.git` directory because every Git operation you perform will result in files changing in that directory (whether you end up in the same state in Git as you were previously or not). This could result in unnecessary invalidation of Docker's cached image layers.

**NOTE:** Unlike `.gitignore` files, `.dockerignore` files do *not* apply recursively to subdirectories. So, for example, while the entry `*.pyc` in a `.gitignore` file will cause Git to ignore `./abc.pyc` and `./def/ghi.pyc`, in a `.dockerignore` file, that entry will cause Docker to ignore only `./abc.pyc`. This is very unfortunate. In order to get the same behaviour from a `.dockerignore` file, you need to add an extra leading `**/` glob pattern — i.e. `**/*.pyc`. For more information on the `.dockerignore` file syntax, see the [Docker documentation](https://docs.docker.com/engine/reference/builder/#dockerignore-file).

### Running other commands
You can skip the execution of the `django-entrypoint.sh` script bootstrapping processes and run other commands by overriding the container's launch command.

You can do this at image build-time by setting the `CMD` directive in your Dockerfile...
```dockerfile
CMD ["django-admin", "runserver"]
```
...or at runtime by passing an argument to the `docker run` command:
```
> $ docker run my-django-bootstrap-image django-admin runserver
```


If the entrypoint script sees a command for `gunicorn` then it will run all bootstrapping processes (database migration, starting Nginx, etc.). Otherwise, the script will execute the command directly. A special case is Celery, which is described next.

## Celery
It's common for Django applications to have [Celery](http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html) workers performing tasks alongside the actual website. Using this image, there are 2 different ways to run Celery:

 1. Run separate containers for Celery (recommended)
 2. Run Celery alongside the Django site inside the same container (simpler)

In most cases it makes sense to run each Celery process in a container separate from the Django/Gunicorn one, so as to follow the rule of one(*-ish*) process per container. But in some cases, running a whole bunch of containers for a relatively simple site may be overkill. Additional containers generally have some overhead in terms of CPU and, especially, memory usage.

Note that, as with Django, your project needs to specify Celery in its `install_requires` in order to use Celery. Celery is not installed in this image by default.

### Option 1: Celery containers
To run a Celery container simply override the container command as described earlier. If the `django-entrypoint.sh` script sees a `celery` command, it will instead run the command using the [`celery-entrypoint.sh`](celery-entrypoint.sh) script. This script switches to the correct user to run Celery and sets some basic config options, depending on which Celery command is being run.

You can override the command in your Dockerfile...
```dockerfile
CMD ["celery", "worker", \
     "--app", "my_django_project", \
     "--loglevel", "info"]
```
...or at runtime:
```
> $ docker run my-django-bootstrap-image celery worker --app my_django_project --loglevel info
```

You can also create dedicated Celery images by overriding the image entrypoint:
```dockerfile
ENTRYPOINT ["dinit", "celery-entrypoint.sh"]
CMD ["worker", \
     "--app", "my_django_project", \
     "--loglevel", "INFO"]
```

### Option 2: Celery in the same container
Celery can be enabled alongside Django/Gunicorn by adjusting a set of environment variables. Setting the `CELERY_APP` variable to the Celery app to run will enable a Celery worker process.

The following environment variables can be used to configure Celery. A number of these can also be configured via the Django project's settings.

#### `CELERY_APP`:
* Required: yes
* Default: none
* Celery option: `-A`/`--app`

#### `CELERY_BROKER`:
* Required: no
* Default: none
* Celery option: `-b`/`--broker`

#### `CELERY_LOGLEVEL`:
* Required: no
* Default: none
* Celery option: `-l`/`--loglevel`

#### `CELERY_CONCURRENCY`:
Note that by default Celery runs as many worker processes as there are processors. **We instead default to 1 worker process** here to ensure containers use a consistent and small amount of resources. If you need to run many worker processes, they should be in separate containers.
* Required: no
* Default: **1**
* Celery option: `-c`/`--concurrency`

#### `CELERY_BEAT`:
Set this option to any non-empty value (e.g. `1`) to have a [Celery beat](http://docs.celeryproject.org/en/latest/userguide/periodic-tasks.html) scheduler process run as well.
* Required: no
* Default: none
* Celery option: n/a

## Other configuration
### Gunicorn
Gunicorn is run with some basic configuration:
* Starts workers under the `gunicorn` user and group
* Listens on a Unix socket at `/var/run/gunicorn/gunicorn.sock`
* Access logs can be logged to stderr by setting the `GUNICORN_ACCESS_LOGS` environment variable to a non-empty value.

Extra settings can be provided by overriding the `CMD` instruction to pass extra parameters to the entrypoint script. For example:
```dockerfile
CMD ["my_django_project.wsgi:application", "--threads", "5", "--timeout", "50"]
```

See all the settings available for gunicorn [here](http://docs.gunicorn.org/en/latest/settings.html). A common setting is the number of Gunicorn workers which can be set with the `WEB_CONCURRENCY` environment variable.

### Nginx
Nginx is set up with mostly default config:
* Access logs are sent to stdout, error logs to stderr and log messages are prefixed with `nginx: ` to differentiate them from Gunicorn log messages
* Listens on port 8000 (and this port is exposed in the Dockerfile)
* Serves files from `/static/` and `/media/`
* All other requests are proxied to the Gunicorn socket

Generally you shouldn't need to adjust Nginx's settings. If you do, the configuration files of interest are at:
* `/etc/nginx/nginx.conf`: Main configuration
* `/etc/nginx/conf.d/django.conf`: Proxy configuration
