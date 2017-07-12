import _thread as thread
import re
import sys
import threading


def resource_name(name, namespace='test'):
    return '{}_{}'.format(namespace, name)


def _quit_function(fn_name):
    # https://stackoverflow.com/a/31667005
    print('{} took too long'.format(fn_name), file=sys.stderr)
    sys.stderr.flush()  # Python 3 stderr is likely buffered.
    # FIXME: Interrupting the main thread is hacky
    thread.interrupt_main()  # raises KeyboardInterrupt


def exit_after(timeout):
    """
    Use as decorator to exit process if function takes longer than s seconds
    https://stackoverflow.com/a/31667005
    """
    def outer(fn):
        def inner(*args, **kwargs):
            timer = threading.Timer(
                timeout, _quit_function, args=[fn.__name__])
            timer.start()
            try:
                result = fn(*args, **kwargs)
            finally:
                timer.cancel()
            return result
        return inner
    return outer


def log_lines_after(container, skip):
    """
    A wrapper around container.logs(stream=True) that skips some number of
    lines before returning output.
    """
    skipped = 0
    for line in container.logs(stream=True):
        if skipped < skip:
            skipped += 1
        else:
            yield line


@exit_after(10)
def wait_for_log_line(container, pattern, skip=0):
    for line in log_lines_after(container, skip=skip):
        line = line.decode('utf-8').rstrip()  # Drop the trailing newline
        if re.search(pattern, line):
            return line


def output_lines(raw_output, encoding='utf-8'):
    return raw_output.decode(encoding).splitlines()


def list_container_processes(container, columns=['pid', 'ruser', 'args']):
    # We use an exec here rather than `container.top()` because we want to run
    # 'ps' inside the container. This is because we want to get PIDs and
    # usernames in the container's namespaces. `container.top()` uses 'ps' from
    # outside the container in the host's namespaces. Note that this requires
    # the container to have a 'ps' that responds to the arguments we give it.
    cols = ','.join(columns)
    ps_output = container.exec_run(['ps', 'ax', '-o', cols])
    ps_lines = output_lines(ps_output)
    ps_lines.pop(0)  # Skip the header
    ps_entries = [line.split(None, max(0, len(columns) - 1))
                  for line in ps_lines]
    # Drop the entry for the ps command itself
    ps_entries = [e for e in ps_entries if e[2] != 'ps ax -o {}'.format(cols)]
    return ps_entries
