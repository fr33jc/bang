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
QUEUES = 'queues'
BUCKETS = 'buckets'
DATABASE_CREDS = 'database_credentials'
DATABASE_SECURITY_GROUPS = 'database_security_groups'
DATABASE_SECURITY_GROUP_RULES = 'database_security_group_rules'
DATABASES = 'databases'
LOAD_BALANCERS = 'load_balancers'
SERVER_SECURITY_GROUPS = 'server_security_groups'
SERVER_SECURITY_GROUP_RULES = 'server_security_group_rules'
SERVER_COMMON_ATTRIBUTES = 'server_common_attributes'
SERVERS = 'servers'
SSH_KEYS = 'ssh_pub_keys'

DYNAMIC_LB_SEC_GROUPS = '_load_balancer_sec_groups'

# This is where the inter-resource dependencies are resolved.  Keep it simple
# until it needs to be more complicated.
#
# Each tuple in the list defines a *stage* - that is, a set of resources that
# can be deployed in parallel.
#
# The stack deployer starts deploying resources in the first tuple, waits for
# all of the resources to be deployed successfully, then moves on to the next
# tuple of resources, etc...  It always waits for all of the deployers in a
# stage/tuple to complete before moving to the next stage/tuple.
#
# If any resource deployment within a stage/tuple is *not* successful, the
# stack deployer does *not* proceed to the next stage - the deployment is
# terminated, and the errors are reported.
STAGES = [
        (
            DATABASE_SECURITY_GROUPS,
            SERVER_SECURITY_GROUPS,
            QUEUES,
            BUCKETS,
            SSH_KEYS,
            ),

        (
            SERVER_SECURITY_GROUP_RULES,
            ),

        (
            DATABASES,
            SERVERS,
            ),
        (
            LOAD_BALANCERS,
            ),
        (
            DATABASE_SECURITY_GROUP_RULES,
            DYNAMIC_LB_SEC_GROUPS,
            ),
        ]

CONVENIENCE_KEYS = [
        SERVER_COMMON_ATTRIBUTES,
        DATABASE_CREDS,
        ]

DYNAMIC_RESOURCE_KEYS = [k for s in STAGES for k in s] + CONVENIENCE_KEYS
