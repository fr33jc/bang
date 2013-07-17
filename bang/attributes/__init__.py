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
Constants for attribute names of the various resources.

Just a place to stash more magic strings.
"""
from . import creds, server, secgroup, tags, database, ssh_key, loadbalancer

# stack attributes
NAME = 'name'
VERSION = 'version'
LOGGING = 'logging'
PLAYBOOKS = 'playbooks'
STACK = 'stack'
DEPLOYER_CREDS = 'deployer_credentials'
KEY = 'key'
SERVER_CLASS = 'server_class'
PROVIDER = 'provider'

# Like chicken fried chicken... this is a way to configure the name of the tag
# in which the combined stack-role (a.k.a. *name*) will be stored.  By default,
# unless this is specified directly in ~/.bangrc, the *name* value will be
# assigned to a tag named "Name" (this is the default tag displayed in the AWS
# management console).  I.e. using Bang defaults, the server named "bar" in the
# stack named "foo" will have the following tags:
#
#     stack:  foo
#     role:   bar
#     Name:   foo-bar
#
# In some cases, admins may have other purposes for the "Name" tag.  If
# ~/.bangrc were to have ``name_tag_name`` set to ``descriptor``, then the
# server described above would have the following tags:
#
#     stack:       foo
#     role:        bar
#     descriptor:  foo-bar
#
# To prevent Bang from assigning the *name* value to a tag, assign an empty
# string to the ``name_tag_name`` attribute in ~/.bangrc.
NAME_TAG_NAME = 'name_tag_name'
