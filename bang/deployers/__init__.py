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
Base classes and definitions for bang deployers (deployable components)
"""
from . import cloud
from .. import resources as R
from ..providers import get_provider
from ..util import log


DEPLOYER_MAP = {
        R.SERVERS: cloud.ServerDeployer,
        R.SERVER_SECURITY_GROUPS: cloud.SecurityGroupDeployer,
        R.SERVER_SECURITY_GROUP_RULES: cloud.SecurityGroupRulesetDeployer,
        R.BUCKETS: cloud.BucketDeployer,
        R.DATABASES: cloud.DatabaseDeployer,
        }


def get_stage_deployers(keys, stack):
    """
    Returns a list of deployer objects that *create* cloud resources.  Each
    member of the list is responsible for provisioning a single stack resource
    (e.g. a virtual server, a security group, a bucket, etc...).

    :param keys:  A list of top-level configuration keys for which to create
        deployers.
    :type keys:  :class:`~collections.Iterable`

    :param config:  A stack object.
    :type config:  :class:`~bang.stack.Stack`

    :rtype:  :class:`list` of :class:`~bang.deployers.deployer.Deployer`

    """
    config = stack.config
    creds = config['deployer_credentials']
    deployers = []
    for res_type in keys:
        res_configs = config.get(res_type)
        if not res_configs:
            continue
        log.debug("Found config for resource type, %s" % res_type)
        for res_config in res_configs:
            pname = res_config['provider']
            provider = get_provider(pname, creds[pname])
            consul = provider.get_consul(res_type)
            if not consul:
                log.warn("%s does not provide %s" % (pname, res_type))
                continue
            deployer = DEPLOYER_MAP[res_type]
            count = res_config.get('instance_count', 1)
            ds = [deployer(stack, res_config, consul) for _ in range(count)]
            deployers.extend(ds)
    return deployers
