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
PUBLIC_IPS = 'public_ip_addresses'
PRIVATE_IPS = 'private_ip_addresses'
SECGROUPS = 'security_groups'
STACK_SECGROUPS = 'stack_security_groups'
EXTRA_SECGROUPS = 'extra_security_groups'
TAGS = 'tags'
NAME = 'name'
ID = 'id'
SCOPES = 'config_scopes'
VARS = 'hostvars'
GROUPS = 'groups'
REGION = 'region_name'
AZ = 'availability_zone'
LAUNCH_TIMEOUT = 'launch_timeout_s'
POST_DELAY = 'post_launch_delay_s'
SSH_KEY = 'ssh_key_name'
PROVIDER = 'provider'

# these are ansible magic vars
INV_NAME = 'inventory_hostname'
INV_NAME_SHORT = 'inventory_hostname_short'
GROUP_NAMES = 'group_names'
PRIVATE_IP = 'private_ip'
