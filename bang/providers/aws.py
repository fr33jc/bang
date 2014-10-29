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

from .. import BangError, TimeoutError, resources as R, attributes as A
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


class EC2SecGroup(object):
    """
    Represents an EC2 security group.

    The :attr:`rules` attribute is a specialized dict whose keys are the
    *normalized* rule definitions, and whose values are EC2 grants which can be
    kwargs-expanded when passing
    :meth:`boto.ec2.securitygroup.SecurityGroup.revoke`.  E.g.:

    .. code-block:: python

        {
            ('tcp', 1, 65535, 'group-foo'): {
                'ip_protocol': 'tcp',
                'from_port': '1',
                'to_port': '65535',
                'src_group': 'group-foo',
                'target': SecurityGroup:group-bar,
                },
            ('tcp', 8080, 8080, '15.183.202.114/32'):  {
                'ip_protocol': 'tcp',
                'from_port': '8080',
                'to_port': '8080',
                'cidr_ip': '15.183.202.114/32',
                'target': SecurityGroup:group-bar,
                },
        }

    This also maintains a reference to the original
    :class:`boto.ec2.securitygroup.SecurityGroup` instance.

    Suitable for returning from :meth:`EC2.find_secgroup`.

    """
    def __init__(self, ec2sg):
        owner_id = ec2sg.owner_id
        rules = {}
        for rule in ec2sg.rules:
            p = rule.ip_protocol
            f = int(rule.from_port)
            t = int(rule.to_port)
            core = {
                    'ip_protocol': p,
                    'from_port': f,
                    'to_port': t,
                    'target': ec2sg,
                    }
            for g in rule.grants:
                parsed = {}
                if g.cidr_ip:
                    s = parsed['cidr_ip'] = str(g.cidr_ip)
                elif g.owner_id == owner_id and g.name == ec2sg.name:
                    parsed['source_self'] = True
                    s = ec2sg.name
                else:
                    parsed['src_group'] = g 
                    s = g.name
                parsed.update(core)
                rules[(p, f, t, s)] = parsed
        self.rules = rules
        self.ec2sg = ec2sg


class EC2(Consul):
    """The consul for the compute service in AWS (EC2)."""
    def __init__(self, *args, **kwargs):
        super(EC2, self).__init__(*args, **kwargs)
        creds = self.provider.creds
        self.access_key_id = creds[A.creds.ACCESS_KEY_ID]
        self.secret_key = creds[A.creds.SECRET_ACCESS_KEY]
        self._ec2 = None

    @property
    def ec2(self):
        if not self._ec2:
            # this connection lets boto pick the default region.  be sure to use
            # set_region() if you need a specific region.
            self._ec2 = boto.connect_ec2(self.access_key_id, self.secret_key)
        return self._ec2

    def set_region(self, region_name):
        log.debug("Setting region to %s" % region_name)
        self._ec2 = boto.ec2.connect_to_region(
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

    def find_running(self, server_attrs, timeout_s):
        return server_attrs

    def create_server(self, basename, disk_image_id, instance_type,
            ssh_key_name, tags=None, availability_zone=None,
            timeout_s=DEFAULT_TIMEOUT_S, **provider_extras):
        """
        Creates a new server instance.  This call blocks until the server is
        created and available for normal use, or :attr:`timeout_s` has elapsed.

        :param str basename:  An identifier for the server.  A random postfix
            will be appended to this basename to work around OpenStack Nova
            REST API limitations.

        :param str disk_image_id:  The identifier of the base disk image to use
            as the rootfs.

        :param str instance_type:  The name of an EC2 instance type.

        :param str ssh_key_name:  The name of the ssh key to inject into the
            target server's ``authorized_keys`` file.  The key must already
            have been registered in the target EC2 region.

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
                **provider_extras
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

    def find_secgroup(self, name):
        """
        Find a security group by name.

        Returns a :class:`EC2SecGroup` instance if found, otherwise returns
        None.

        """
        res = self.ec2.get_all_security_groups(filters={'group-name': name})
        if res:
            return EC2SecGroup(res[0])

    def create_secgroup(self, name, description):
        """
        Creates a new server security group.

        :param str name:  The name of the security group to create.
        :param str description:  A short description of the group.

        """
        return self.ec2.create_security_group(name, description)
        log.debug("... created group %s" % name)

    def create_secgroup_rule(self, protocol, from_port, to_port,
            source, target):
        """
        Creates a new server security group rule.

        :param str protocol:  E.g. ``tcp``, ``icmp``, etc...
        :param int from_port:  E.g. ``1``
        :param int to_port:  E.g. ``65535``
        :param str source:
        :param str target:  The target security group.  I.e. the group in which
            this rule should be created.

        """
        kwargs = {
            'ip_protocol': protocol,
            'from_port': from_port,
            'to_port': to_port
        }
        sg = self.find_secgroup(target).ec2sg
        if not sg:
            raise BangError("Security group not found, %s" % target)
        if '/' in source:
            # Treat as cidr (/ is mask)
            kwargs['cidr_ip'] = source
        else:
            kwargs['src_group'] = self.find_secgroup(source).ec2sg
        sg.authorize(**kwargs)

    def delete_secgroup_rule(self, rule_def):
        """Deletes the security group rule identified by :attr:`rule_def`"""
        sg = rule_def.pop('target')
        sg.revoke(**rule_def)


class S3(Consul):
    """The consul for the storage service in AWS (S3)."""
    def __init__(self, *args, **kwargs):
        super(S3, self).__init__(*args, **kwargs)
        creds = self.provider.creds
        self.access_key_id = creds[A.creds.ACCESS_KEY_ID]
        self.secret_key = creds[A.creds.SECRET_ACCESS_KEY]
        self._s3 = None

    @property
    def s3(self):
        if not self._s3:
            # this connection lets boto pick the default region.  be sure to use
            # set_region() if you need a specific region.
            self._s3 = boto.connect_s3(self.access_key_id, self.secret_key)
        return self._s3

    def set_region(self, region_name):
        log.debug("Setting region to %s" % region_name)
        self._s3 = boto.s3.connect_to_region(
                region_name,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_key,
                )

    def create_bucket(self, name):
        """
        Creates a new S3 bucket.
        :param str name: E.g. 'mybucket'
        """
        log.info('Creating bucket %s...' % name)
        self.s3.create_bucket(name)



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
