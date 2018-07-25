# docker-django-bootstrap

[![Docker Pulls](https://img.shields.io/docker/pulls/praekeltfoundation/django-bootstrap.svg?style=flat-square)](https://hub.docker.com/r/praekeltfoundation/django-bootstrap/)
[![Travis branch](https://img.shields.io/travis/praekeltfoundation/docker-django-bootstrap/develop.svg?style=flat-square)](https://travis-ci.org/praekeltfoundation/docker-django-bootstrap)

Dockerfile for quickly running Django projects in a Docker container.

Run [Django](https://www.djangoproject.com) projects from source using [Gunicorn](http://gunicorn.org) and [Nginx](http://nginx.org).

## Usage
#### Step 1: Get your Django project in shape
There are a few ways that your Django project needs to be set up in order to be compatible with this Docker image.

**setup.py**  
Your project must have a [`setup.py`](https://packaging.python.org/distributing/#setup-py). All dependencies need to be listed in the [`install_requires`](https://packaging.python.org/distributing/#install-requires).

Your dependencies should include at least:
* `Django`
* `celery` (if using)
* ...but **not** `gunicorn`

Django *isn't* installed in this image as different projects may use different versions of Django. Celery is completely optional.

Gunicorn is the only Python package installed in this image. It is kept up-to-date and tested here so you should not be pinning the `gunicorn` package in your application. Gunicorn is considered a deployment detail and your Django project should not rely on its use.

**Static files**  
Your project's [static files](https://docs.djangoproject.com/en/1.10/howto/static-files/) must be set up as follows in your Django settings:
* `STATIC_URL = '/static/'`
* `STATIC_ROOT` = `'static'` (relative) or `'/app/static'` (absolute)

**Media files**  
If your project makes use of user-uploaded media files, it must be set up as follows:
* `MEDIA_URL = '/media/'`
* `MEDIA_ROOT` = `'media'` (relative) or `'/app/media'` (absolute)

> The `staticfiles` and `mediafiles` directories are also used for serving static and media files, but this is deprecated.

***Note:*** Any files stored in directories called `static`, `staticfiles`, `media`, or `mediafiles` in the project root directory (`/app`) will be served by Nginx. Do not store anything here that you do not want the world to see.

**Django settings file**
You'll probably want to make your Django settings file *Docker-friendly* so that the app is easier to deploy on container-based infrastructure. There are a lot of ways to do this and many project-specific considerations, but the [settings file](example/mysite/docker_settings.py) in the example project is a good place to start and has lots of documentation.

#### Step 2: Write a Dockerfile
In the root of the repo for your Django project, add a Dockerfile for the project. For example, this file could contain:
```dockerfile
FROM praekeltfoundation/django-bootstrap

COPY . /app
RUN pip install -e .

ENV DJANGO_SETTINGS_MODULE my_django_project.settings
ENV CELERY_APP my_django_project

RUN django-admin collectstatic --noinput

CMD ["my_django_project.wsgi:application"]
```

Let's go through these lines one-by-one:
 1. The `FROM` instruction here tells us which image to base this image on. We use the `django-bootstrap` base image.
 2. Copy the source (in the current working directory-- `.`) of your project into the image (`/app` in the container)
 3. Execute (`RUN`) a `pip` command inside the container to install your project from the source
 4. We set the `DJANGO_SETTINGS_MODULE` environment variable so that Django knows where to find its settings. This is necessary for any `django-admin` commands to work.
 5. *Optional:* If you are using Celery, setting the `CELERY_APP` environment variable lets Celery know what app instance to use (i.e. you don't have to provide [`--app`](http://docs.celeryproject.org/en/latest/reference/celery.bin.celery.html#cmdoption-celery-a)).
 6. *Optional:* If you need to run any build-time tasks, such as collecting static assets, now's the time to do that.
 7. We set the container command (`CMD`) to a list of arguments that will be passed to `gunicorn`. We need to provide Gunicorn with the [`APP_MODULE`](http://docs.gunicorn.org/en/stable/run.html?highlight=app_module#gunicorn), so that it knows which WSGI app to run.*

> Note that previously the way to do point 5 was to set the `APP_MODULE` environment variable. That still works, but is no longer the recommended way and is deprecated.

By default, the [`django-entrypoint.sh`](django-entrypoint.sh) script is run when the container is started. This script runs a once-off `django-admin migrate` to update the database schemas and then launches `nginx` and `gunicorn` to run the application.

The script also allows you to create a Django super user account if needed. Setting the `SUPERUSER_PASSWORD` environment variable will result in a Django superuser account being made with the `admin` username. This will only happen if no `admin` user exists.

By default the script will run the migrations when starting up. This may not be desirable in all situations. If you want to run migrations separately using `django-admin` then setting the `SKIP_MIGRATIONS` environment variable will result in them not being run.

#### Step 3: Add a `.dockerignore` file (if copying in the project source)
If you are copying the full source of your project into your Docker image (i.e. doing `COPY . /app`), then it is important to add a `.dockerignore` file.

Add a file called `.dockerignore` to the root of your project. A good start is just to copy in the [`.dockerignore` file](example/.dockerignore) from the example Django project in this repo.

When copying in the source of your project, some of those files probably *aren't* needed inside the Docker image you're building. We tell Docker about those unneeded files using a `.dockerignore` file, much like how one would tell Git not to track files using a `.gitignore` file.

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
CMD ["celery", "worker"]
```
...or at runtime:
```
> $ docker run my-django-bootstrap-image celery worker
```

You can also create dedicated Celery images by overriding the image entrypoint:
```dockerfile
ENTRYPOINT ["dinit", "celery-entrypoint.sh"]
CMD ["worker"]
```
The above assume that you have set the `CELERY_APP` environment variable.

### Option 2: Celery in the same container
Celery can be run alongside Django/Gunicorn by adjusting a set of environment variables. Setting the `CELERY_WORKER` variable to a non-empty value will enable a Celery worker process. Similarly, setting the `CELERY_BEAT` variable will enable a Celery beat process.

#### `CELERY_WORKER`:
Set this option to any non-empty value (e.g. `1`) to have a [Celery worker](http://docs.celeryproject.org/en/latest/userguide/workers.html)  process run. This requires that `CELERY_APP` is set.
* Required: no
* Default: none
* Celery option: n/a

#### `CELERY_BEAT`:
Set this option to any non-empty value (e.g. `1`) to have a [Celery beat](http://docs.celeryproject.org/en/latest/userguide/periodic-tasks.html) process run. This requires that `CELERY_APP` is set.
* Required: no
* Default: none
* Celery option: n/a

Note that when running a Celery worker in this way, the process pool implementation used is the ['solo' pool](http://docs.celeryproject.org/en/latest/internals/reference/celery.concurrency.solo.html). This means that instead of a pair of processes (master/worker) for the Celery worker, there is just one process. This saves on resources.

The worker is always single-process (the `--concurrency` option is ignored) and is **blocking**. A number of worker configuration options can't be used with this pool implementation. See the [worker guide](http://docs.celeryproject.org/en/latest/userguide/workers.html) in the Celery documentation for more information.

### Celery environment variable configuration
The following environment variables can be used to configure Celery, but, other than the `CELERY_APP` variable, you should configure Celery in your Django settings file. See the example project's [settings file](example/mysite/docker_settings.py) for an example of how to do that.

#### `CELERY_APP`:
* Required: yes, if `CELERY_WORKER` or `CELERY_BEAT` is set.
* Default: none
* Celery option: `-A`/`--app`

<details>
  <summary>Deprecated environment variables</summary>
  <blockquote><b>NOTE</b>: The following 3 environment variables are deprecated. They will continue to work for now but it is recommended that you set these values in your Django settings file rather.</blockquote>

  <h4><code>CELERY_BROKER</code>:</h4>
  <ul>
    <li>Required: no</li>
    <li>Default: none</li>
    <li>Celery option: <code>-b</code>/<code>--broker</code></li>
  </ul>

  <h4><code>CELERY_LOGLEVEL</code>:</h4>
  <ul>
  <li>Required: no</li>
  <li>Default: none</li>
  <li>Celery option: <code>-l</code>/<code>--loglevel</code></li>
  </ul>

  <h4><code>CELERY_CONCURRENCY</code>:</h4>
  <ul>
  <li>Required: no</li>
  <li>Default: <b>1</b></li>
  <li>Celery option: <code>-c</code>/<code>--concurrency</code></li>
  </ul>

</details>

#### A note on worker processes
By default Celery runs as many worker processes as there are processors. **We instead default to 1 worker process** in this image to ensure containers use a consistent and small amount of resources no matter what kind of host the containers happen to run on.

If you need more Celery worker processes, you have the choice of either upping the processes per container or running multiple container instances.

## Other configuration
### Gunicorn
Gunicorn is run with some basic configuration:
* Starts workers under the `django` user and group
* Listens on a Unix socket at `/var/run/gunicorn/gunicorn.sock`
* Access logs can be logged to stderr by setting the `GUNICORN_ACCESS_LOGS` environment variable to a non-empty value.

Extra settings can be provided by overriding the `CMD` instruction to pass extra parameters to the entrypoint script. For example:
```dockerfile
CMD ["my_django_project.wsgi:application", "--threads", "5", "--timeout", "50"]
```

See all the settings available for gunicorn [here](http://docs.gunicorn.org/en/latest/settings.html). A common setting is the number of Gunicorn workers which can be set with the `WEB_CONCURRENCY` environment variable.

### Nginx
Nginx is set up with mostly default config:
* Access logs are sent to stdout, error logs to stderr and log messages are formatted to be JSON-compatible for easy parsing.
* Listens on port 8000 (and this port is exposed in the Dockerfile)
* Has gzip compression enabled for most common, compressible mime types
* Serves files from `/static/` and `/media/`
* All other requests are proxied to the Gunicorn socket

Generally you shouldn't need to adjust Nginx's settings. If you do, the configuration is split into several files that can be overridden individually:
* `/etc/nginx/nginx.conf`: Main configuration (including logging and gzip compression)
* `/etc/nginx/conf.d/`
  * `django.conf`: The primary server configuration
  * `django.conf.d/`
    * `upstream.conf`: Upstream connection to Gunicorn
    * `locations/*.conf`: Each server location (static, media, root)
    * `maps/*.conf`: Nginx maps for setting variables

We make a few adjustments to Nginx's default configuration to better work with Gunicorn. See the [config file](nginx/conf.d/django.conf) for all the details. One important point is that we consider the `X-Forwarded-Proto` header, when set to the value of `https`, as an indicator that the client connection was made over HTTPS and is secure. Gunicorn considers a few more headers for this purpose, `X-Forwarded-Protocol` and `X-Forwarded-Ssl`, but our Nginx config is set to remove those headers to prevent misuse.
