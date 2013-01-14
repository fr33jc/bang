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
import random
import string

# at least RDS appears to force lowercase even if you pass in mixed case
_AWS_NAME_CHARS = string.lowercase + string.digits


class Provider(object):
    """The base class for all providers."""
    def __init__(self, creds):
        self.creds = creds

        # Minimal attempt to prevent obvious postfix duplication
        self.component_names = []

    def gen_component_name(self, basename, postfix_length=13):
        """
        Creates a resource identifier with a random postfix.  This is an
        attempt to minimize name collisions in provider namespaces.

        :param str basename:  The string that will be prefixed with the stack
            name, and postfixed with some random string.

        :param int postfix_length:  The length of the postfix to be appended.

        """
        def newcname():
            postfix = ''.join(
                    random.choice(_AWS_NAME_CHARS)
                    for i in xrange(postfix_length)
                    )
            return '%s-%s' % (basename, postfix)
        cname = newcname()
        while cname in self.component_names:
            cname = newcname()
        self.component_names.append(cname)
        return cname

    def get_consul(self, resource_type):
        """
        Returns an object that a :class:`~bang.deployers.deployer.Deployer`
        uses to control resources of :attr:`resource_type`.

        :param str service:  Any of the resources defined
            in :mod:`bang.resources`.

        """
        consul = self.CONSUL_MAP.get(resource_type)
        if consul:
            return consul(self)


class Consul(object):
    """
    The base class for all service consuls.

    Not really the boss of anything, but conveys intent-from-above to foreign
    entities (e.g. OpenStack Nova/Swift, AWS EC2/S3/RDS, etc...).  Also
    communicates the state of the world back up to the boss.

    """

    def __init__(self, provider):
        self.provider = provider
