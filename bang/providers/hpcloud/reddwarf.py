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
"""
Customizations and enhancements of the upstream python-reddwarfclient library
to support hpcloud extensions.
"""
import reddwarfclient
import reddwarfclient.base


class DBSecurityGroup(reddwarfclient.base.Resource):
    def grant(self, source_cidr):
        """
        Allows connections from :attr:`source_cidr`.

        :param str source_cidr:  The source IP range from which to allow
            connections.

        """
        self.manager.api.secgroup_rules.create(self.id, source_cidr)


class DBSecurityGroups(reddwarfclient.base.ManagerWithFind):
    """Manages db security groups"""

    resource_class = DBSecurityGroup

    def list(self):
        """
        List all security groups.

        :rtype: :class:`list` of :class:`DBSecurityGroup`.

        """
        # that's right, the root key uses an underscore, not a hyphen.  the
        # hpcloud api docs show it as a hyphen.
        return self._list("/security-groups", "security_groups")


class DBSecurityGroupRule(reddwarfclient.base.Resource):
    def delete(self):
        """Deletes this rule"""
        self.manager.delete(self.id)


class DBSecurityGroupRules(reddwarfclient.base.ManagerWithFind):
    """Manages db security group rules"""

    resource_class = DBSecurityGroupRule

    def create(self, dbsecgroup_id, source_cidr, port=3306):
        """
        Creates a security group rule.

        :param str dbsecgroup_id:  The ID of the security group in which this
            rule should be created.
        :param str source_cidr:  The source IP address range from which access
            should be allowed.
        :param int port:  The port number used by db clients to connect to the
            db server.  This would have been specified at db instance creation
            time.

        :rtype:  :class:`DBSecurityGroupRule`.

        """
        body = {
                "security_group_rule": {
                    "security_group_id": dbsecgroup_id,
                    "cidr": source_cidr,
                    "from_port": port,
                    "to_port": port,
                    }
                }
        return self._create("/security-group-rules", body,
                "security_group_rule")

    def delete(self, rule_id):
        """
        Deletes a rule from a security group.

        :param str rule_id:  The rule ID.

        """
        self._delete("/security-group-rules/%s" % rule_id)


class HPDbaas(reddwarfclient.Dbaas):
    def __init__(self, *args, **kwargs):
        super(HPDbaas, self).__init__(*args, **kwargs)
        self.secgroups = DBSecurityGroups(self)
        self.secgroup_rules = DBSecurityGroupRules(self)
