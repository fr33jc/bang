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
from .deployer import Deployer


class ServerDeployer(Deployer):
    """
    Default deployer that can be used for any servers that are already deployed
    and do not need special deployment logic (e.g. traditional server rooms,
    manually deployed cloud servers).

    Example of a minimal configuration for a manually provisioned app server::

        my_app_server:
          hostname: my_hostname_or_ip_address
          groups:
          - ansible_inventory_group_1
          - ansible_inventory_group_n
          config_scopes:
          - config_scope_1
          - config_scope_n

    """
    def __init__(self, *args, **kwargs):
        super(ServerDeployer, self).__init__(*args, **kwargs)
        self.phases = [(True, self.add_to_inventory)]
        self.inventory_phases = [self.add_to_inventory]

    def add_to_inventory(self):
        """Adds this server and its hostvars to the ansible inventory."""
        self.stack.add_host(self.hostname, self.groups, self.hostvars)
