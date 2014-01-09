# Copyright 2013 - John Calixto, Steve McLellan
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
from .... import attributes as A, resources as R
from .nova_ext import DiabloVolumeManager
from .. import HPCloud, HPDbaas
from ...openstack import Nova

def fix_hp_addrs(server):
    """
    Works around hpcloud's peculiar "all ip addresses are returned as private
    even though one is public" bug.  This is also what the official hpfog gem
    does in the ``Fog::Compute::HP::Server#public_ip_address`` method.

    :param dict server:  Contains the server ID, a list of public IP addresses,
        and a list of private IP addresses.

    """
    fixed = {A.server.ID: server[A.server.ID]}
    both = server.get(A.server.PRIVATE_IPS)
    if both:
        fixed[A.server.PUBLIC_IPS] = [both[1]]
        fixed[A.server.PRIVATE_IPS] = [both[0]]
    return fixed

class HPNova(Nova):
    def find_servers(self, *args, **kwargs):
        """
        Wraps :meth:`bang.providers.openstack.Nova.find_servers` to apply
        hpcloud specialization, namely pulling IP addresses from the hpcloud's
        non-standard return values.

        """
        servers = super(HPNova, self).find_servers(*args, **kwargs)
        return map(fix_hp_addrs, servers)

    def create_server(self, *args, **kwargs):
        """
        Wraps :meth:`bang.providers.openstack.Nova.create_server` to apply
        hpcloud specialization, namely pulling IP addresses from the hpcloud's
        non-standard return values.

        """
        # hpcloud's management console stuffs all of its tags in a "tags" tag.
        # populate it with the stack and role values here only at server
        # creation time.  what users do with it after server creation is up to
        # them.
        tags = kwargs['tags']
        tags[A.tags.TAGS] = ','.join([
                tags.get(A.tags.STACK, ''),
                tags.get(A.tags.ROLE, ''),
                ])
        # Don't create an explicit floating IP; gets one 
        # automatically
        if 'floating_ip' not in kwargs:
            kwargs['floating_ip'] = False
        s = super(HPNova, self).create_server(*args, **kwargs)
        return fix_hp_addrs(s)


class HPCloudV12(HPCloud):

    REDDWARF_SERVICE_TYPE = 'hpext:dbaas'
    REDDWARF_CLIENT_CLASS = HPDbaas

    def __init__(self, *args, **kwargs):
        super(HPCloudV12, self).__init__(*args, **kwargs)
        self.CONSUL_MAP[R.SERVERS] = HPNova

    def _get_nova_client(self):
        nc = super(HPCloudV12, self)._get_nova_client()
        nc.volumes = DiabloVolumeManager(nc)
        return nc


