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
import boto
import boto.ec2
from boto.exception import EC2ResponseError
import time

from .. import TimeoutError, resources as R, attributes as A
from ..util import log, poll_with_timeout
from .bases import Provider, Consul


DEFAULT_TIMEOUT_S = 120


def server_to_dict(server):
    """
    Returns the :class:`dict` representation of a server object.

    The returned :class:`dict` is meant to be consumed by
    :class:`~bang.deployers.cloud.ServerDeployer` objects.

    """
    return {
            A.server.ID: server.id,
            A.server.PUBLIC_IPS: [server.public_dns_name],
            A.server.PRIVATE_IPS: [server.private_dns_name],
            }


class EC2(Consul):
    """The consul for the compute service in AWS (EC2)."""
    def __init__(self, *args, **kwargs):
        super(EC2, self).__init__(*args, **kwargs)
        creds = self.provider.creds
        self.access_key_id = creds[A.creds.ACCESS_KEY_ID]
        self.secret_key = creds[A.creds.SECRET_ACCESS_KEY]

        # this connection lets boto pick the default region.  be sure to use
        # set_region() if you need a specific region.
        self.ec2 = boto.connect_ec2(self.access_key_id, self.secret_key)

    def set_region(self, region_name):
        log.debug("Setting region to %s" % region_name)
        self.ec2 = boto.ec2.connect_to_region(
                region_name,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_key,
                )

    def find_servers(self, tags, running=True):
        """
        Returns any servers in the region that have tags that match the
        key-value pairs in :attr:`tags`.

        :param Mapping tags:  A mapping object in which the keys are the tag
            names and the values are the tag values.

        :param bool running:  A flag to limit server list to instances that are
            actually *running*.

        :rtype:  :class:`list` of :class:`dict` objects.  Each :class:`dict`
            describes a single server instance.

        """
        filters = dict([('tag:%s' % key, val) for key, val in tags.items()])
        if running:
            filters['instance-state-name'] = 'running'

        res = self.ec2.get_all_instances(filters=filters)
        instances = [server_to_dict(i) for r in res for i in r.instances]
        log.debug('instances: %s' % instances)
        return instances

    def create_server(self, basename, disk_image_id, instance_type,
            ssh_key_name, tags=None, availability_zone=None,
            timeout_s=DEFAULT_TIMEOUT_S, **kwargs):
        """
        Creates a new server instance.  This call blocks until the server is
        created and available for normal use, or :attr:`timeout_s` has elapsed.

        :param str basename:  An identifier for the server.  A random postfix
            will be appended to this basename to work around OpenStack Nova
            REST API limitations.

        :param str disk_image_id:  The identifier of the base disk image to use
            as the rootfs.

        :param str instance_type:  The name of an OpenStack instance type, or
            *flavor*.  This is specific to the OpenStack provider installation.

        :param str ssh_key_name:  The name of the ssh key to inject into the
            target server's ``authorized_keys`` file.  The key must already
            have been registered with the OpenStack Nova provider.

        :param tags:  Up to 5 key-value pairs of arbitrary strings to use as
            *tags* for the server instance.
        :type tags:  :class:`Mapping`

        :param str availability_zone:  The name of the availability zone in
            which to place the server.

        :param float timeout_s:  The number of seconds to poll for an active
            server before failing.  Defaults to ``0`` (i.e. Expect server to be
            active immediately).

        :rtype:  :class:`dict`

        """
        log.info(
                'Launching server %s... this could take a while...'
                % basename
                )
        res = self.ec2.run_instances(
                disk_image_id,
                instance_type=instance_type,
                key_name=ssh_key_name,
                placement=availability_zone,
                disable_api_termination=True,
                **kwargs
                )
        instance = res.instances[0]

        # we're too fast for EC2... slow down a little bit, twice
        time.sleep(2)

        def apply_tags():
            try:
                for key, val in tags.items():
                    instance.add_tag(key, val)
                return True
            except EC2ResponseError:
                pass
        if not poll_with_timeout(timeout_s, apply_tags, 5):
            raise TimeoutError('Could not tag server %s' % instance.id)

        def find_running_instance():
            if instance.update() == 'running':
                return instance
        running = poll_with_timeout(timeout_s, find_running_instance, 5)
        if not running:
            raise TimeoutError('Could not launch server within allotted time.')
        return server_to_dict(running)


class S3(Consul):
    pass


class RDS(Consul):
    pass


class AWS(Provider):

    CONSUL_MAP = {
            R.SERVERS: EC2,
            R.SERVER_SECURITY_GROUPS: EC2,
            R.SERVER_SECURITY_GROUP_RULES: EC2,
            R.BUCKETS: S3,
            R.DATABASES: RDS,
            }
