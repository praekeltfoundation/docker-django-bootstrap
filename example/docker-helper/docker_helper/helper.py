import logging
import warnings

import docker

from .utils import resource_name

log = logging.getLogger(__name__)


class DockerHelper(object):
    def setup(self):
        # Filter out unclosed socket ResourceWarnings. These happen due to
        # requests' connection pooling and spam the logs unnecessarily:
        # https://github.com/requests/requests/issues/1882
        warnings.filterwarnings(
            action='ignore', message='unclosed', category=ResourceWarning)

        self._client = docker.client.from_env()
        self._network = self._client.networks.create(
            resource_name('default'), driver='bridge')
        self._container_ids = []

    def teardown(self):
        # Remove all containers
        for container_id in self._container_ids:
            # Check if the container exists before trying to remove it
            try:
                container = self._client.containers.get(container_id)
            except docker.errors.NotFound:
                continue

            print("Warning container '{}' was still running".format(
                container.name))

            self.stop_and_remove_container(container)

        # Remove the network
        self._network.remove()

        # Restore unclosed ResourceWarnings
        warnings.filterwarnings(
            action='default', message='unclosed', category=ResourceWarning)

    def create_container(self, name, image, **kwargs):
        container_name = resource_name(name)
        log.info("Creating container '{}'...".format(container_name))
        container = self._client.containers.create(
            image, name=container_name, detach=True, network=self._network.id,
            **kwargs)

        # FIXME: Hack to make sure the container has the right network aliases.
        # If we don't specify a network when the container is created then the
        # default bridge network is attached which we don't want.
        self._network.disconnect(container)
        self._network.connect(container, aliases=[name])

        # Keep a reference to created containers to make sure they are cleaned
        # up
        self._container_ids.append(container.id)

        return container

    def start_container(self, container):
        log.info("Starting container '{}'...".format(container.name))
        container.start()

        container.reload()
        log.debug("Container '{}' has status '{}'".format(
            container.name, container.status))
        assert container.status == 'running'

    def stop_container(self, container, timeout=5):
        log.info("Stopping container '{}'...".format(container.name))
        container.stop(timeout=timeout)

        container.reload()
        log.debug("Container '{}' has status '{}'".format(
            container.name, container.status))
        assert container.status != 'running'

    def remove_container(self, container, force=True):
        log.info("Removing container '{}'...".format(container.name))
        container.remove(force=force)

    def stop_and_remove_container(
            self, container, stop_timeout=5, remove_force=True):
        self.stop_container(container, timeout=stop_timeout)
        self.remove_container(container, force=remove_force)

    def pull_image_if_not_found(self, image):
        try:
            self._client.images.get(image)
            log.debug("Image '{}' found".format(image))
        except docker.errors.ImageNotFound:
            log.info("Pulling image '{}'...".format(image))
            self._client.images.pull(image)

    def get_container_host_port(self, container, container_port, index=0):
        # FIXME: Bit of a hack to get the port number on the host
        inspection = self._client.api.inspect_container(container.id)
        return (inspection['NetworkSettings']['Ports']
                [container_port][index]['HostPort'])
