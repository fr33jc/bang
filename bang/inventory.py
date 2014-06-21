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
from .util import deep_merge_dicts
import ansible.inventory
from ansible.inventory.group import Group
from ansible.inventory.host import Host


def get_ansible_groups(group_map):
    """
    Constructs a list of :class:`ansible.inventory.group.Group` objects from a
    map of lists of host strings.

    """
    # Much of this logic is cribbed from
    # ansible.inventory.script.InventoryScript
    all_hosts = {}
    group_all = Group('all')
    group_all.add_host(Host('127.0.0.1'))
    groups = [group_all]
    for gname, hosts in group_map.iteritems():
        g = Group(gname)
        for host in hosts:
            h = all_hosts.get(host, Host(host))
            all_hosts[host] = h
            g.add_host(h)
            group_all.add_host(h)
        group_all.add_child_group(g)
        groups.append(g)
    return groups


class BangsibleInventory(ansible.inventory.Inventory):
    def __init__(self, groups, hostvars):
        super(BangsibleInventory, self).__init__(None)
        self.groups = get_ansible_groups(groups)

        # Prepopulate the cache.  The base Inventory only gathers host vars as
        # necessary (to avoid repeated execs of the inventory script), and
        # caches them in ``self._vars_per_host``.  By the time bang needs a
        # BangsibleInventory, it already has all of the hostvars so we just set
        # the cache to be the hostvars dict.
        self._bang_vars_per_host = hostvars

    def is_file(self):
        return False

    def get_variables(self, hostname, vault_password=None):
        hvars = super(BangsibleInventory, self).get_variables(
                hostname,
                vault_password,
                )
        deep_merge_dicts(hvars, self._bang_vars_per_host[hostname])
        return hvars
