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


@exit_after(10)
def wait_for_log_line(container, pattern):
    for line in container.logs(stream=True):
        line = line.decode('utf-8').rstrip()  # Drop the trailing newline
        if re.search(pattern, line):
            return line


def output_lines(raw_output, encoding='utf-8'):
    decoded = raw_output.decode(encoding)
    lines = decoded.split('\n')
    # Remove extra newline at end of output
    lines.pop()
    return lines


def list_container_processes(container, columns=['pid', 'ruser', 'args']):
    ps_output = container.exec_run(['ps', 'ax', '-o', ','.join(columns)])
    ps_lines = output_lines(ps_output)
    ps_lines.pop(0)  # Skip the header
    ps_lines.pop()  # Drop the entry for the ps command itself

    return [line.split(None, max(0, len(columns) - 1)) for line in ps_lines]
