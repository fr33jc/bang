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
from .. import attributes as A
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


class ServerDeployer(RegionedDeployer):

    def __init__(self, *args, **kwargs):
        super(ServerDeployer, self).__init__(*args, **kwargs)
        self.namespace = self.stack.get_namespace(self.name)
        self.server_attrs = None
        self.phases = [
                (True, self.find_existing),
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
        for addy in self.server_attrs[A.server.PUBLIC_IPS]:
            self.stack.add_host(addy, self.groups, self.hostvars)


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
        current = {}
        for rule in sg.rules:
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
            current[parsed] = rule['id']

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
        for rule_id in self.delete_these_rules:
            self.consul.delete_secgroup_rule(rule_id)
            log.info("Revoked: %s" % rule_id)


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
