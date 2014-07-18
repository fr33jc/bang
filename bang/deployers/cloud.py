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
import time
from .. import resources as R, attributes as A
from ..providers import get_provider
from ..util import log
from .deployer import Deployer


class BaseDeployer(Deployer):
    """Base class for all cloud resource deployers"""
    def __init__(self, stack, config, consul):
        super(BaseDeployer, self).__init__(stack, config)
        self._consul = consul

    @property
    def consul(self):
        return self._consul


class RegionedDeployer(BaseDeployer):
    """Deployer that automatically sets its region"""
    @property
    def consul(self):
        self._consul.set_region(self.region_name)
        return self._consul


class SSHKeyDeployer(RegionedDeployer):
    """
    Registers SSH keys with cloud providers so they can be used at
    server-launch time.

    """
    def __init__(self, *args, **kwargs):
        super(SSHKeyDeployer, self).__init__(*args, **kwargs)
        self.found = False
        self.phases = [
                (True, self.find_existing),
                (lambda: not self.found, self.register),
                ]

    def find_existing(self):
        """Searches for an existing SSH key matching the name."""
        self.found = self.consul.find_ssh_pub_key(self.name)

    def register(self):
        """Registers SSH key with provider."""
        log.info('Installing ssh key, %s' % self.name)
        self.consul.create_ssh_pub_key(self.name, self.key)


class ServerDeployer(RegionedDeployer):

    def __init__(self, *args, **kwargs):
        super(ServerDeployer, self).__init__(*args, **kwargs)
        self.namespace = self.stack.get_namespace(self.name)
        self.server_attrs = None
        self.phases = [
                (True, self.find_existing),
                (lambda: self.server_attrs, self.wait_for_running),
                (lambda: not self.server_attrs, self.create),
                (True, self.add_to_inventory),
                ]
        self.inventory_phases = [
                self.find_existing,
                self.add_to_inventory,
                ]

    def find_existing(self):
        """
        Searches for existing server instances with matching tags.  To match,
        the existing instances must also be "running".

        """
        instances = self.consul.find_servers(self.tags)
        maxnames = len(instances)
        while instances:
            i = instances.pop(0)
            server_id = i[A.server.ID]
            if self.namespace.add_if_unique(server_id):
                log.info('Found existing server, %s' % server_id)
                self.server_attrs = i
                break
            if len(self.namespace.names) >= maxnames:
                break
            instances.append(i)

    def wait_for_running(self):
        """Waits for found servers to be operational"""
        self.server_attrs = self.consul.find_running(
                self.server_attrs,
                self.launch_timeout_s,
                )

    def create(self):
        """Launches a new server instance."""
        self.server_attrs = self.consul.create_server(
                "%s-%s" % (self.stack.name, self.name),
                self.disk_image_id,
                self.instance_type,
                self.ssh_key_name,
                tags=self.tags,
                availability_zone=self.availability_zone,
                timeout_s=self.launch_timeout_s,
                security_groups=self.security_groups,
                )
        log.debug('Post launch delay: %d s' % self.post_launch_delay_s)
        time.sleep(self.post_launch_delay_s)

    def add_to_inventory(self):
        """Adds host to stack inventory"""
        if not self.server_attrs:
            return
        for addy in self.server_attrs[A.server.PUBLIC_IPS]:
            self.stack.add_host(addy, self.groups, self.hostvars)


class CloudManagerServerDeployer(ServerDeployer):
    """
    Server deployer for cloud management services.

    Cloud management services like RightScale and Scalr provide constructs like
    server templates (a.k.a. roles) to bundle together disk image ids with
    on-server configuration automation (e.g. RightScripts, Scalr scripts).
    This deployer replaces the low-level provisioning functionality in the base
    :class:`ServerDeployer` with a :meth:`create` method that is more suited to
    the high-level launching mechanism provided by cloud management services.
    """
    def __init__(self, *args, **kwargs):
        super(CloudManagerServerDeployer, self).__init__(*args, **kwargs)
        self.server_def = None
        self.phases = [
                (True, self.create_stack),
                (True, self.find_existing),
                (lambda: self.server_attrs, self.wait_for_running),
                (lambda: not self.server_attrs, self.find_def),
                (lambda: not (self.server_attrs or self.server_def),
                    self.define),
                (lambda: not self.server_attrs, self.create),
                (True, self.add_to_inventory),
                ]

    def create_stack(self):
        self.consul.create_stack(self.stack.name)

    def find_def(self):
        server_defs = self.consul.find_server_defs(self.name)
        maxnames = len(server_defs)
        while server_defs:
            href = server_defs.pop(0)
            if self.namespace.add_if_unique(href):
                log.info('Found existing server def, %s' % href)
                self.server_def = href
                break
            if len(self.namespace.names) >= maxnames:
                break
            server_defs.append(href)

    def define(self):
        """Defines a new server."""
        self.server_def = self.consul.define_server(
                self.name,
                self.server_tpl,
                self.server_tpl_rev,
                self.instance_type,
                self.ssh_key_name,
                tags=self.tags,
                availability_zone=self.availability_zone,
                security_groups=self.security_groups,
                )
        log.debug('Defined server %s' % self.server_def)

    def create(self):
        self.server_attrs = self.consul.create_server(
                self.server_def,
                self.inputs,
                timeout_s=self.launch_timeout_s,
                )
        log.debug('Post launch delay: %d s' % self.post_launch_delay_s)
        time.sleep(self.post_launch_delay_s)


class SecurityGroupDeployer(RegionedDeployer):
    def __init__(self, *args, **kwargs):
        super(SecurityGroupDeployer, self).__init__(*args, **kwargs)
        self.group = None
        self.phases = [
                (True, self.find_existing),
                (lambda: not self.group, self.create),
                ]
        self.attrs = {}

    def find_existing(self):
        """Finds existing secgroup"""
        self.group = self.consul.find_secgroup(self.name)

    def create(self):
        """Creates a new security group"""
        self.consul.create_secgroup(self.name, self.description)


class SecurityGroupRulesetDeployer(RegionedDeployer):
    def __init__(self, *args, **kwargs):
        super(SecurityGroupRulesetDeployer, self).__init__(*args, **kwargs)
        self.create_these_rules = []
        self.delete_these_rules = []
        self.phases = [
                (True, self.find_existing),
                (lambda: self.create_these_rules or self.delete_these_rules,
                    self.apply_rule_changes),
                ]

    def find_existing(self):
        """
        Finds existing rule in secgroup.

        Populates ``self.create_these_rules`` and ``self.delete_these_rules``.

        """
        sg = self.consul.find_secgroup(self.name)

        current = sg.rules
        log.debug('Current rules: %s' % current)
        log.debug('Intended rules: %s' % self.rules)
        exp_rules = []
        for rule in self.rules:
            exp = (
                    rule[A.secgroup.PROTOCOL],
                    rule[A.secgroup.FROM],
                    rule[A.secgroup.TO],
                    rule[A.secgroup.SOURCE],
                    )
            exp_rules.append(exp)
            if exp in current:
                del current[exp]
            else:
                self.create_these_rules.append(exp)

        self.delete_these_rules.extend(current.itervalues())

        log.debug('Create these rules: %s' % self.create_these_rules)
        log.debug('Delete these rules: %s' % self.delete_these_rules)

    def apply_rule_changes(self):
        """
        Makes the security group rules match what is defined in the Bang
        config file.

        """
        # TODO: add error handling
        for rule in self.create_these_rules:
            args = rule + (self.name, )
            self.consul.create_secgroup_rule(*args)
            log.info("Authorized: %s" % str(rule))
        for rule in self.delete_these_rules:
            self.consul.delete_secgroup_rule(rule)
            log.info("Revoked: %s" % rule)


class BucketDeployer(BaseDeployer):
    def __init__(self, *args, **kwargs):
        super(BucketDeployer, self).__init__(*args, **kwargs)
        self.phases = [
                (True, self.create),
                ]

    def create(self):
        """Creates a new bucket"""
        self.consul.create_bucket("%s-%s" % (self.stack.name, self.name))


class DatabaseDeployer(BaseDeployer):
    def __init__(self, *args, **kwargs):
        super(DatabaseDeployer, self).__init__(*args, **kwargs)
        self.instance_name = "%s-%s" % (self.stack.name, self.name)
        self.db_attrs = None
        self.phases = [
                (True, self.find_existing),
                (lambda: not self.db_attrs, self.create),
                (True, self.add_to_inventory),
                ]
        self.inventory_phases = [
                self.find_existing,
                self.add_to_inventory,
                ]

    def find_existing(self):
        """
        Searches for existing db instance with matching name.  To match, the
        existing instance must also be "running".

        """
        self.db_attrs = self.consul.find_db_instance(self.instance_name)

    def create(self):
        """Creates a new database"""
        self.db_attrs = self.consul.create_db(
                self.instance_name,
                self.instance_type,
                self.admin_username,
                self.admin_password,
                db_name=self.db_name,
                storage_size_gb=self.storage_size,
                timeout_s=self.launch_timeout_s,
                )

    def add_to_inventory(self):
        """Adds db host to stack inventory"""
        host = self.db_attrs.pop(A.database.HOST)
        self.stack.add_host(
                host,
                self.groups,
                self.db_attrs
                )


class LoadBalancerDeployer(RegionedDeployer):
    """
    Cloud-managed load balancer deployer. Assumes a consul able
    to create and discover LB instances, as well as match existing
    backend 'nodes' to a list it's given. It is assumed only a single
    'instance' per distinct load balancer needs to be created (i.e.
    that any elasticity is handled by the cloud service).

    Example config::

      load_balancers:
        test_balancer:
          balance_server_name: server_defined_in_servers_section
          region: region-1.geo-1
          provider: hpcloud
          backend_port: '8080'
          protocol: tcp
          port: '443'

    """

    def __init__(self, *args, **kwargs):
        super(LoadBalancerDeployer, self).__init__(*args, **kwargs)
        self.instance_name = "%s-%s" % (self.stack.name, self.name)
        self.lb_attrs = None
        self.delete_these_nodes = []
        self.add_these_nodes = []
        self.phases = [
                (True, self.find_existing),
                (lambda: not self.lb_attrs, self.create),
                (True, self.add_to_inventory),
                (True, self.configure_nodes),
                ]
        self.inventory_phases = [
                self.find_existing,
                self.add_to_inventory,
                ]

    def find_existing(self):
        """
        Searches for existing load balancer instance with matching name.
        Doesn't populate 'details' including the nodes and virtual IPs
        """
        self.lb_attrs = self.consul.find_lb_by_name(self.instance_name)

    def create(self):
        """Creates a new load balancer"""
        required_nodes = self._get_required_nodes()
        self.lb_attrs = self.consul.create_lb(
                self.instance_name,
                protocol=self.protocol,
                port=self.port,
                nodes=required_nodes,
                node_port=str(self.backend_port),
                algorithm=getattr(self, 'algorithm', None)
                )

    def configure_nodes(self):
        """Ensure that the LB's nodes matches the stack"""
        # Since load balancing runs after server provisioning,
        # the servers should already be created regardless of
        # whether this was a preexisting load balancer or not.
        # We also have the existing nodes, because add_to_inventory
        # has been called already
        required_nodes = self._get_required_nodes()

        log.debug(
                "Matching existing lb nodes to required %s (port %s)"
                % (", ".join(required_nodes), self.backend_port)
                )

        self.consul.match_lb_nodes(
            self.lb_attrs[A.loadbalancer.ID],
            self.lb_attrs[A.loadbalancer.NODES_KEY],
            required_nodes,
            self.backend_port)

        self.lb_attrs = self.consul.lb_details(
                self.lb_attrs[A.loadbalancer.ID]
                )

    def _get_required_nodes(self):
        required_nodes = set()
        for host, attrs in self.stack.groups_and_vars.dicts.items():
            if attrs.get(A.SERVER_CLASS) == self.balance_server_name:
                required_nodes.add(host)
        return required_nodes

    def add_to_inventory(self):
        """Adds lb IPs to stack inventory"""
        if self.lb_attrs:
            self.lb_attrs = self.consul.lb_details(
                    self.lb_attrs[A.loadbalancer.ID]
                    )
            host = self.lb_attrs['virtualIps'][0]['address']
            self.stack.add_lb_secgroup(self.name, [host], self.backend_port)
            self.stack.add_host(
                    host,
                    [self.name],
                    self.lb_attrs
                    )


class LoadBalancerSecurityGroupsDeployer(SecurityGroupRulesetDeployer):
    def __init__(self, *args, **kwargs):
        super(LoadBalancerSecurityGroupsDeployer, self).__init__(
                *args, **kwargs)
        self.group = None
        self.attrs = {}

    def find_existing(self):
        # Prepopulate rules from the LB stack variables
        lb_entry = self.stack.lb_sec_groups.dicts.get(self.load_balancer)
        if not lb_entry:
            raise Exception(
                "No load balancer host found in stack for '%s'"
                % self.load_balancer
                )
        for host in lb_entry['hosts']:
            # Create a rule for this LB. Need a mask or nova interprets it
            # as a group rule rather than IP rule
            host = host + "/32"
            rule = {
                    A.secgroup.PROTOCOL: 'tcp',
                    A.secgroup.FROM: lb_entry['port'],
                    A.secgroup.TO: lb_entry['port'],
                    A.secgroup.SOURCE: host,
                   }
            self.rules.append(rule)

        super(LoadBalancerSecurityGroupsDeployer, self).find_existing()

DEFAULT_DEPLOYER_MAP = {
        R.SSH_KEYS: SSHKeyDeployer,
        R.SERVERS: ServerDeployer,
        R.SERVER_SECURITY_GROUPS: SecurityGroupDeployer,
        R.SERVER_SECURITY_GROUP_RULES: SecurityGroupRulesetDeployer,
        R.BUCKETS: BucketDeployer,
        R.DATABASES: DatabaseDeployer,
        R.LOAD_BALANCERS: LoadBalancerDeployer,
        R.DYNAMIC_LB_SEC_GROUPS: LoadBalancerSecurityGroupsDeployer,
        }

CLOUD_MANAGER_DEPLOYER_OVERRIDES = {
        'rightscale': {
            R.SERVERS: CloudManagerServerDeployer,
            },
        }


def get_deployer(provider, res_type):
    deployer = CLOUD_MANAGER_DEPLOYER_OVERRIDES.get(provider, {}).get(res_type)
    if not deployer:
        deployer = DEFAULT_DEPLOYER_MAP[res_type]
    return deployer


def get_deployers(res_config, res_type, stack, creds):
    pname = res_config[A.PROVIDER]
    provider = get_provider(pname, creds[pname])
    consul = provider.get_consul(res_type)
    if not consul:
        log.warn("%s does not provide %s" % (pname, res_type))
        return
    deployer = get_deployer(pname, res_type)
    count = res_config.get('instance_count', 1)
    return [deployer(stack, res_config, consul) for _ in range(count)]
