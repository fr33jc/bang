# Copyright 2012 - John Calixto
#
# This file is part of bang.
#
# bang is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# bang is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with bang.  If not, see <http://www.gnu.org/licenses/>.
import argparse
import atexit
import bang
import collections
import copy
import json
import logging
import multiprocessing
import time
import re
import subprocess
import sys
import textwrap
from datetime import datetime
from logging.handlers import BufferingHandler

import boto
from boto.s3.key import Key
from logutils.queue import QueueHandler, QueueListener


CONSOLE_LOGGING_FORMAT = '%(asctime)s %(levelname)8s %(processName)s - %(message)s'

# use the multiprocessing logger so when we start parallelizing the
# deploys, we have a seamless transition.
_mlog = multiprocessing.get_logger()
log = _mlog.manager.getLogger('.'.join((_mlog.name, 'bang')))


# this is stolen from python2.7 to have support in 2.6 - noqa
class NullHandler(logging.Handler):
    """
    This handler does nothing. It's intended to be used to avoid the
    "No handlers could be found for logger XXX" one-off warning. This is
    important for library code, which may contain code to log events. If a user
    of the library does not configure logging, the one-off warning might be
    produced; to avoid this, the library developer simply needs to instantiate
    a NullHandler and add it to the top-level logger of the library module or
    package.
    """
    def handle(self, record):
        pass

    def emit(self, record):
        pass

    def createLock(self):
        self.lock = None

# give this logger at least one handler to avoid pesky warnings for bang
# commands that don't actually care about logging
_mlog.addHandler(NullHandler())
log.addHandler(NullHandler())
del _mlog


class StrictAttrBag(object):
    """
    Generic attribute container that makes constructor arguments available as
    object attributes.

    Checks :meth:`__init__` argument names against lists of *required* and
    *optional* attributes.

    """
    def __init__(self, **kwargs):
        for reqk in self.REQUIRED_ATTRS:
            if reqk not in kwargs:
                raise TypeError("Missing required argument, %s" % reqk)
            setattr(self, reqk, kwargs.pop(reqk))

        for k, v in kwargs.items():
            if k not in self.OPTIONAL_ATTRS:
                raise TypeError("Unknown argument, %s" % k)
            setattr(self, k, v)


class SharedMap(object):
    """
    A multiprocess-safe :class:`Mapping` object that can be used to return
    values from child processes.

    """
    def __init__(self, manager):
        self.lists = manager.dict()
        self.dicts = manager.dict()
        self.lock = multiprocessing.Lock()

    def append(self, list_name, value):
        """Appends :attr:`value` to the list named :attr:`list_name`."""
        with self.lock:
            l = self.lists.get(list_name)
            if l:
                l.append(value)
            else:
                l = [value]
            self.lists[list_name] = l

    def merge(self, dict_name, values):
        """
        Performs deep-merge of :attr:`values` onto the :class:`Mapping` object
        named :attr:`dict_name`.

        If :attr:`dict_name` does not yet exist, then a deep copy of
        :attr:`values` is assigned as the initial mapping object for the given
        name.

        :param str dict_name:  The name of the dict onto which the values
            should be merged.

        """

        with self.lock:
            d = self.dicts.get(dict_name)
            if d:
                deep_merge_dicts(d, values)
            else:
                d = copy.deepcopy(values)
            self.dicts[dict_name] = d


class SharedNamespace(object):
    """
    A multiprocess-safe namespace that can be used to coordinate naming similar
    resources uniquely.  E.g. when searching for existing nodes in a cassandra
    cluster, you can use this SharedNamespace to make sure other processes
    aren't looking at the same node.
    """
    def __init__(self, manager):
        self.names = manager.list()
        self.lock = multiprocessing.Lock()

    def add_if_unique(self, name):
        """
        Returns ``True`` on success.

        Returns ``False`` if the name already exists in the namespace.
        """
        with self.lock:
            if name not in self.names:
                self.names.append(name)
                return True
        return False


class JSONFormatter(logging.Formatter):
    def __init__(self, config):
        logging.Formatter.__init__(self)
        self.stack = config.get('stack', 'anonymous')

    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).isoformat()
        out = {
                'level': record.levelname,
                'message': record.message,
                'timestamp': timestamp,
                'stack': self.stack,
                'pid': record.process,
                'process_name': record.processName,
                }
        return '%s\n' % json.dumps(out)


class ColoredConsoleFormatter(logging.Formatter):
    def format(self, record):
        pre = logging.Formatter.format(self, record)
        return '\033[38;5;%dm%s\033[0;37m' % (
                (record.process * 4) % 210 + 20,
                pre,
                )


class S3Handler(BufferingHandler):
    """
    Buffers all logging events, then uploads them all at once "atexit" to a
    single file in S3.
    """
    def __init__(self, bucket, prefix=''):
        BufferingHandler.__init__(self, 0)
        self.bucket = bucket
        self.prefix = prefix

    def shouldFlush(self, record):
        return False

    def flush(self):
        payload = ''
        while len(self.buffer) > 0:
            record = self.buffer.pop(0)
            if record.levelno >= self.level:
                payload += self.format(record)
        if payload:
            conn = boto.connect_s3()
            bucket = conn.get_bucket(self.bucket)
            key = Key(bucket)
            key.key = '/'.join((self.prefix, 'bang-%f' % time.time()))
            key.content_type = 'application/json'
            key.set_contents_from_string(payload)


def initialize_logging(config):
    multiprocessing.current_process().name = 'Stack'
    cfg = config.get('logging', {})
    console_level = cfg.get('console_level', 'INFO')
    log.setLevel(console_level)

    # log to s3 if there's a destination specified in the config
    bucket = cfg.get('s3_bucket')
    if bucket:
        json_formatter = JSONFormatter(config)
        s3_handler = S3Handler(bucket, cfg.get('s3_prefix', ''))
        s3_handler.setFormatter(json_formatter)
        s3_handler.setLevel(logging.INFO)

        # The parent process is the only one that actually buffers the log
        # records in memory and writes them out to s3.  The child processes
        # send all of their log records to the parent's queue.
        #
        # Using the QueueHandler and QueueListener classes from logutils-0.3.2
        # here since they're the implementations in future versions of stdlib
        # logging anyway (logutils is the "backports from Py3k logging"
        # library).
        queue = multiprocessing.Queue()
        ql = QueueListener(queue, s3_handler)

        def cleanup():
            ql.stop()
            s3_handler.flush()
        atexit.register(cleanup)
        ql.start()

        qh = QueueHandler(queue)
        log.addHandler(qh)

    # also log to stderr
    if sys.stderr.isatty():
        formatter = ColoredConsoleFormatter(CONSOLE_LOGGING_FORMAT)
    else:
        formatter = logging.Formatter(CONSOLE_LOGGING_FORMAT)
    handler = logging.StreamHandler()  # default stream is stderr
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)
    log.addHandler(handler)
    log.debug('Logging initialized.')


def poll_with_timeout(timeout_s, break_func, wake_every_s=60):
    """
    Calls :attr:`break_func` every :attr:`wake_every_s` seconds for a total
    duration of :attr:`timeout_s` seconds, or until :attr:`break_func` returns
    something other than ``None``.

    If :attr:`break_func` returns anything other than ``None``, that value is
    returned immediately.

    Otherwise, continues polling until the timeout is reached, then returns
    ``None``.

    """
    time_slept = 0
    if wake_every_s > 60:
        msg = '... sleeping for %0.2f minutes' % (wake_every_s / 60.0)
    else:
        msg = '... sleeping for %d seconds' % wake_every_s
    res = break_func()
    while res is None and time_slept < timeout_s:
        log.debug(msg)
        time.sleep(wake_every_s)
        time_slept += wake_every_s
        res = break_func()
    return res


def parse_args(arg_config, alt_args=None):
    """
    ``alt_args`` is an optional list of strings to use *instead* of sys.argv.
    """
    parser = argparse.ArgumentParser(
            prog=arg_config.get('prog'),
            description=textwrap.dedent(arg_config['description']),
            formatter_class=argparse.RawTextHelpFormatter,
            )
    for ac in arg_config['arguments']:
        args = ac[:-1]
        kwargs = ac[-1]
        parser.add_argument(*args, **kwargs)
    return parser.parse_args(alt_args)


SECRET_PATTERN = re.compile(r'(\s*(\S*(password|pwd|key|secret|god)\S*)\s*:\s*)\S+')
SECRET_WHITELIST = ('ssh_key', 'key_pair')


def redact_secrets(line):
    """
    Returns a sanitized string for any ``line`` that looks like it contains a
    secret (i.e. matches SECRET_PATTERN).
    """
    def redact(match):
        if match.group(2) in SECRET_WHITELIST:
            return match.group(0)
        return match.group(1) + 'TOO_TOO_SEXY'
    return SECRET_PATTERN.sub(redact, line)


def bump_version_tail(oldver):
    """
    Takes any dot-separated version string and increments the rightmost field
    (which it expects to be an integer).
    """
    head, tail = oldver.rsplit('.', 1)
    return '%s.%d' % (head, (int(tail) + 1))


def count_to_deploy(stack, descriptor, config_count):
    """
    takes the max of config_count and number of instances running
    with this stack/descriptor combo
    """
    live_count = count_by_tag(stack, descriptor)
    if config_count > live_count:
        live_count = config_count

    return live_count


def count_by_tag(stack, descriptor):
    """
    Returns the count of currently running or pending instances
    that match the given stack and deployer combo
    """
    ec2_conn = boto.ec2.connection.EC2Connection()
    resses = ec2_conn.get_all_instances(
                    filters={
                        'tag:stack': stack,
                        'tag:descriptor': descriptor
                    })
    instance_list_raw = list()
    [[instance_list_raw.append(x) for x in res.instances] for res in resses]
    instance_list = [x for x in instance_list_raw if state_filter(x)]
    instances = len(instance_list)
    return instances


def state_filter(instance):
    """
    Helper function for count_by_tag
    """
    if instance.state == 'running' or instance.state == 'pending':
        return True
    else:
        return False


def deep_merge_dicts(base, incoming):
    """
    Performs an *in-place* deep-merge of key-values from :attr:`incoming`
    into :attr:`base`.  No attempt is made to preserve the original state of
    the objects passed in as arguments.

    :param dict base:  The target container for the merged values.  This will
        be modified *in-place*.
    :type base:  Any :class:`dict`-like object

    :param dict incoming:  The container from which incoming values will be
        copied.  Nested dicts in this will be modified.
    :type incoming:  Any :class:`dict`-like object

    :rtype:  None

    """
    for ki, vi in incoming.iteritems():
        if (ki in base
                and isinstance(vi, collections.MutableMapping)
                and isinstance(base[ki], collections.MutableMapping)
                ):
            deep_merge_dicts(base[ki], vi)
        else:
            base[ki] = vi


def fork_exec(cmd_list, input_data=None):
    """
    Like the subprocess.check_*() helper functions, but tailored to bang.

    ``cmd_list`` is the command to run, and its arguments as a list of strings.

    ``input_data`` is the optional data to pass to the command's stdin.

    On success, returns the output (i.e. stdout) of the remote command.

    On failure, raises BangError with the command's stderr.
    """
    # log.debug('fork_exec: cmd_list = %s, input_data = ^%s^' %
    #         (cmd_list, input_data))
    p = subprocess.Popen(
            cmd_list,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            )
    out = p.communicate(input_data)
    if p.returncode != 0:
        raise bang.BangError('ret: %d, stdout: ^%s^, stderr: ^%s^' %
                (p.returncode, out[0], out[1]))
    return out[0]
