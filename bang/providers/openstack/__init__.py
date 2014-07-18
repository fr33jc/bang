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
from functools import wraps
from novaclient.client import Client as NovaClient
from swiftclient.client import Connection as SwiftConn
from reddwarfclient import Dbaas

from ... import BangError, TimeoutError, resources as R, attributes as A
from ...util import log, poll_with_timeout
from ..bases import Provider, Consul


DEFAULT_TIMEOUT_S = 120
DEFAULT_STORAGE_SIZE_GB = 20


def server_to_dict(server):
    """
    Returns the :class:`dict` representation of a server object.

    The returned :class:`dict` is meant to be consumed by
    :class:`~bang.deployers.cloud.ServerDeployer` objects.

    """
    def get_ips_for_server(server):
        public_ips = []
        private_ips = []
        def address_is_public(address):
            return address['OS-EXT-IPS:type'] == 'floating'
        def address_is_private(address):
            return not address_is_public(address)

        for network, addresses in server.addresses.iteritems():
            # TODO: is this right? Can have private floating ips
            public = filter(address_is_public, addresses)
            private = filter(address_is_private, addresses)
            public_ips.extend(public)
            private_ips.extend(private)
        return private_ips, public_ips

    addresses = server.addresses
    pub = addresses.get('public', [])
    priv = addresses.get('private', [])

    if not pub and not priv:
        # Openstack 13.5?
        priv, pub = get_ips_for_server(server)

    return {
            A.server.ID: server.id,
            A.server.PUBLIC_IPS: [a['addr'] for a in pub],
            A.server.PRIVATE_IPS: [a['addr'] for a in priv],
            }


def db_to_dict(db):
    """
    Returns the :class:`dict` representation of a database object.

    The returned :class:`dict` is meant to be consumed by
    :class:`~bang.deployers.cloud.ServerDeployer` objects.

    """
    return {
            A.database.HOST: db.hostname,
            A.database.PORT: db.port,
            }


class NovaSecGroup(object):
    """
    Represents a Nova security group.

    The :attr:`rules` attribute is a specialized dict whose keys are the
    *normalized* rule definitions, and whose values are the *Nova-specific*
    rule IDs.  E.g.::

        {
            ('tcp', 1, 65535, 'group-foo'): 400459,
            ('tcp', 8080, 8080, '15.183.202.114/32'): 424099,
        }

    Suitable for returning from :meth:`Nova.find_secgroup`.

    """
    def __init__(self, novasg):
        rules = {}
        for rule in novasg.rules:
            src_group = rule.get('group')
            # TODO: allow for groups with different tenant ids.
            if src_group:
                src = src_group['name']
            else:
                src = rule['ip_range'].get('cidr', '')
            parsed = (
                    rule.get('ip_protocol'),
                    rule.get('from_port'),
                    rule.get('to_port'),
                    src,
                    )
            rules[parsed] = rule['id']
        self.rules = rules
        self.novasg = novasg


class Nova(Consul):
    """The consul for the OpenStack compute service."""

    def __init__(self, *args, **kwargs):
        super(Nova, self).__init__(*args, **kwargs)
        self.nova = self.provider.nova_client

    def set_region(self, region_name):
        client = self.nova.client
        management_url = client.service_catalog.url_for(
            attr='region',
            filter_value=region_name,
            service_type=client.service_type,
            )
        client.set_management_url(management_url.rstrip('/'))

    def find_ssh_pub_key(self, name):
        """
        Returns ``True`` if an SSH key named :attr:`name` is found.

        Otherwise returns ``False``.

        :rtype:  :class:`bool`

        """
        return bool(self.nova.keypairs.findall(name=name))

    def create_ssh_pub_key(self, name, key):
        """
        Installs the public SSH key under the name :attr:`name`.

        Once installed, the key can be referenced when creating new server
        instances.

        """
        self.nova.keypairs.create(name, key)

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
        log.debug("Finding instances with tags: %s" % tags)
        search_opts = {}
        if running:
            search_opts['status'] = 'ACTIVE'
        all_servers = self.nova.servers.list(search_opts=search_opts)
        servers = []
        for s in all_servers:
            md = s.metadata
            mismatches = [k for k, v in tags.items() if v != md.get(k)]
            if mismatches:
                continue
            servers.append(server_to_dict(s))
        return servers

    def find_running(self, server_attrs, timeout_s):
        return server_attrs

    def create_server(self, basename, disk_image_id, instance_type,
            ssh_key_name, tags=None, availability_zone=None,
            timeout_s=DEFAULT_TIMEOUT_S, floating_ip=True,
            **kwargs):
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

        :param bool floating_ip:  Allocate a floating IP (in
            openstack 13.5 this doesn't happen automatically, so only
            don't do it if you know what you're doing)


        :rtype:  :class:`dict`

        """
        nova = self.nova
        name = self.provider.gen_component_name(basename)
        log.info('Launching server %s... this could take a while...' % name)
        flavor = nova.flavors.find(name=instance_type)
        server = nova.servers.create(
                name,
                disk_image_id,
                flavor,
                key_name=ssh_key_name,
                meta=tags,
                availability_zone=availability_zone,
                **kwargs
                )

        def find_active():
            s = nova.servers.get(server.id)
            if s and s.status == 'ACTIVE':
                return s

        instance = poll_with_timeout(timeout_s, find_active, 5)
        if not instance:
            raise TimeoutError(
                    'Server %s failed to launch within allotted time.'
                    % server.id
                    )

        if floating_ip:
            log.info('Creating floating ip for %s', name)
            floating_ip = nova.floating_ips.create()
            server.add_floating_ip(floating_ip)
            log.info('Created floating ip %s for %s', floating_ip.ip, name)

        return server_to_dict(instance)

    def find_secgroup(self, name):
        """
        Find a security group by name.

        Returns a :class:`NovaSecGroup` instance if found, otherwise returns
        None.

        """
        groups = self.nova.security_groups.findall(name=name)
        if groups:
            return NovaSecGroup(groups[0])

    def create_secgroup(self, name, desc):
        """
        Creates a new server security group.

        :param str name:  The name of the security group to create.
        :param str desc:  A short description of the group.

        """
        self.nova.security_groups.create(name, desc)

    def create_secgroup_rule(self, protocol, from_port, to_port,
            source, target):
        """
        Creates a new server security group rule.

        :param str protocol:  E.g. ``tcp``, ``icmp``, etc...
        :param int from_port:  E.g. ``1``
        :param int to_port:  E.g. ``65535``
        :param str source:
        :param str target:

        """
        nova = self.nova

        def get_id(gname):
            sg = nova.security_groups.find(name=gname)
            if not sg:
                raise BangError("Security group not found, %s" % gname)
            return str(sg.id)

        kwargs = {
                'ip_protocol': protocol,
                'from_port': str(from_port),
                'to_port': str(to_port),
                'parent_group_id': get_id(target),
                }
        if '/' in source:
            kwargs['cidr'] = source
        else:
            kwargs['group_id'] = get_id(source)
            # not sure if this is an openstack hack or an hpcloud hack, but
            # this is definitely required to get it working on hpcloud:
            kwargs['cidr'] = 'null'
        nova.security_group_rules.create(**kwargs)

    def delete_secgroup_rule(self, rule_id):
        """Deletes the security group rule identified by :attr:`rule_id`"""
        self.nova.security_group_rules.delete(rule_id)


class Swift(Consul):
    def find_buckets(self, prefix):
        _, buckets = self.provider.swift_client.get_account(prefix=prefix)
        # TODO: standardize the return value across providers
        return buckets

    def create_bucket(self, name, headers=None):
        """
        Creates a bucket named :attr:`name`.

        :param dict headers:  Any headers to use when performing the HTTP PUT.

        """
        self.provider.swift_client.put_container(name, headers)


class RedDwarf(Consul):
    def find_db_instance(self, name, running=True):
        """
        Searches for a db instance named :attr:`name`.

        :param str name:  The name of the target db instance

        :param bool running:  A flag to only look for instances that are
            actually *running*.

        :rtype:  :class:`dict`

        """
        found = None
        for i in self.provider.reddwarf_client.instances.list():
            if i.name == name:
                if not running:  # don't care if it's running or not
                    found = i
                if i.status == 'running':
                    found = i
        if found:
            log.info("Found existing db, %s (%s)" % (found.name, found.id))
            return db_to_dict(found)

    def _create_db(self, instance_name, instance_type,
            storage_size_gb):
        rd = self.provider.reddwarf_client
        flavor = rd.flavors.find(name=instance_type)
        log.info('Launching db server %s...' % instance_name)
        # TODO:  Upstream RedDwarf has some notion of ``databases`` and
        # ``users``, both of which are optional args to the create() call
        # below.  Figure out what that means in practice.
        return rd.instances.create(
                instance_name,
                flavor.links[0]['href'],
                {'size': storage_size_gb}
                )

    def _poll_instance_status(self, db, timeout_s):
        log.info('Polling for db status...')

        def find_active():
            i = self.provider.reddwarf_client.instances.get(db.id)
            if i and i.status == 'running':
                return i

        instance = poll_with_timeout(timeout_s, find_active, 20)
        if not instance:
            raise TimeoutError(
                    'DB %s failed to launch within allotted time.' % db.id
                    )
        return instance

    def create_db(self, instance_name, instance_type, admin_username,
            admin_password, security_groups=None, db_name=None,
            storage_size_gb=DEFAULT_STORAGE_SIZE_GB,
            timeout_s=DEFAULT_TIMEOUT_S):
        """
        Creates a database instance.

        This method blocks until the db instance is active, or until
        :attr:`timeout_s` has elapsed.

        :param str instance_name:  A name to assign to the db instance.

        :param str instance_type:  The server instance type (e.g. ``medium``).

        :param str admin_username:  The admin username.

        :param str admin_password:  The admin password.

        :param security_groups:  A list of security groups in which to place
            the db instance.
        :type security_groups:  :class:`~collections.Iterable`

        :param str db_name:  The database name.  If this is not specified, the
            database will be named the same as the :attr:`instance_name`.

        :param int storage_size_gb:  The size of the storage volume in GB.

        :param float timeout_s:  The number of seconds to poll for an active
            database server before failing.

        :rtype:  :class:`dict`

        """
        # TODO: investigate what upstream RedDwarf does for admin users
        return db_to_dict(
                self._poll_instance_status(
                    self._create_db(instance_name, instance_type,
                        storage_size_gb),
                    timeout_s
                    )
                )


def authenticated(f):
    """Decorator that authenticates to Keystone automatically."""
    @wraps(f)
    def new_f(self, *args, **kwargs):
        if not self.nova_client.client.auth_token:
            self.authenticate()
        return f(self, *args, **kwargs)
    return new_f


class OpenStack(Provider):

    CONSUL_MAP = {
            R.SERVERS: Nova,
            R.SSH_KEYS: Nova,
            R.SERVER_SECURITY_GROUPS: Nova,
            R.SERVER_SECURITY_GROUP_RULES: Nova,
            R.BUCKETS: Swift,
            R.DATABASES: RedDwarf,
            }

    REDDWARF_SERVICE_TYPE = 'reddwarf'
    REDDWARF_CLIENT_CLASS = Dbaas

    def __init__(self, creds):
        super(OpenStack, self).__init__(creds)
        self._client = None
        self._swift = None
        self._reddwarf = None
        self.authenticate()

    @property
    @authenticated
    def os_auth_token(self):
        """Authentication token returned from Keystone."""
        return self.nova_client.client.auth_token

    @property
    @authenticated
    def os_catalog(self):
        """
        Service catalog returned from Keystone (Identity Service).

        This is specific to OpenStack providers.
        """
        return self.nova_client.client.service_catalog.catalog

    def _get_nova_client(self):
        args = self.get_nova_client_args()
        kwargs = self.get_nova_client_kwargs()
        return NovaClient(*args, **kwargs)

    @property
    def nova_client(self):
        """
        Each of the OpenStack client libraries (i.e. the ``python-*client``
        projects that live under https://github.com/openstack/) has its own way
        of connecting to the identity service (keystone).

        The object returned here is a :class:`novaclient.v1_1.client.Client`.

        """
        if not self._client:
            self._client = self._get_nova_client()
        return self._client

    @property
    def swift_client(self):
        if not self._swift:
            url = self.nova_client.client.service_catalog.url_for(
                    service_type='object-store'
                    )
            sconn = SwiftConn(
                    'usetoken',
                    'usetoken',
                    'usetoken',
                    preauthurl=url,
                    auth_version='2.0',
                    preauthtoken=self.os_auth_token
                    )
            self._swift = sconn
        return self._swift

    @property
    def reddwarf_client(self):
        if not self._reddwarf:
            url = self.nova_client.client.service_catalog.url_for(
                    service_type=self.REDDWARF_SERVICE_TYPE
                    )
            cli = self.REDDWARF_CLIENT_CLASS('usenova', 'usenova',
                    self.creds.get(A.creds.TENANT))
            cli.client.authenticate_with_token(self.os_auth_token, url)
            self._reddwarf = cli
        return self._reddwarf

    def get_nova_client_args(self):
        creds = self.creds
        # novaclient supports authentication plugins, so username + password
        # might not be the only set of credentials used to authenticate, so we
        # won't validate their existence here.  we do need tenant_name though.
        tenant_name = self.creds.get('tenant_name')
        if tenant_name:
            return [
                    '1.1',
                    creds.get('username', ''),
                    creds.get('password', ''),
                    tenant_name,
                    ]
        raise BangError("Need tenant_name to authenticate!")

    def get_nova_client_kwargs(self):
        creds = self.creds
        kwargs = dict((k, creds.get(k)) for k in ('auth_url', 'region_name'))
        # region_name is optional, but auth_url is required:
        if not kwargs['auth_url']:
            raise BangError("Need auth_url to authenticate!")
        return kwargs

    def authenticate(self):
        log.info("Authenticating to OpenStack...")
        self.nova_client.authenticate()
