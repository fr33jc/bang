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
from .aws import AWS

PROVIDER_MAP = {
        'aws': AWS,
        }

_POSSIBLE_PROVIDERS = (
        ('hpcloud_v12', 'bang.providers.hpcloud.v12', 'HPCloudV12'),
        ('hpcloud_v13', 'bang.providers.hpcloud', 'HPCloud'),
        ('openstack', 'bang.providers.openstack', 'OpenStack'),
        ('rightscale', 'bang.providers.rs', 'RightScale'),
        )

for key, mod_name, provider in _POSSIBLE_PROVIDERS:
    try:
        _mod = __import__(mod_name, fromlist=[provider], level=0)
        PROVIDER_MAP[key] = getattr(_mod, provider)
    except ImportError:
        pass


# provider object cache:
_PROVIDERS = {}


def get_provider(name, creds):
    """
    Generates and memoizes a :class:`~bang.providers.provider.Provider` object
    for the given name.

    :param str name:  The provider name, as given in the config stanza.  This
        token is used to find the
        appropriate :class:`~bang.providers.provider.Provider`.

    :param dict creds:  The credentials dictionary that is appropriate for the
        desired provider.  Typically, a sub-dict from the main stack config.

    :rtype:  :class:`~bang.providers.provider.Provider`

    """
    p = _PROVIDERS.get(name)
    if not p:
        provider = PROVIDER_MAP.get(name)
        if not provider:
            if name == 'hpcloud':
                print "## Warning - 'hpcloud' is not currently supported as" \
                    "a provider; use hpcloud_v12 or hpcloud_v13. See " \
                    "release notes."
            raise Exception("No provider matches %s; check imports" % name)
        p = provider(creds)
        _PROVIDERS[name] = p
    return p
