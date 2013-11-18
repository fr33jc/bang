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

This module contains the top-level config file attributes including those that
are typically placed in ~/.bangrc.
"""
from . import creds, server, secgroup, tags, database, ssh_key, loadbalancer

#: The stack name.  Its value is used to tag servers and other cloud resources.
NAME = 'name'

#: The stack version.  Often, you need a global version of a stack in a
#: playbook.  E.g. when a web client wants to query a web service for API
#: compatibility, the playbooks could configure the web service to report this
#: stack version.
VERSION = 'version'

#: The ordered list of playbooks to run *after* provisioning the cloud
#: resources.
PLAYBOOKS = 'playbooks'

#: The resource provider (e.g. ``aws``, ``hpcloud``).  Values for the
#: ``provider`` attribute will be used to look up the appropriate
#: :class:`~bang.providers.bases.Provider` subclass to use when instantiating
#: the associated resource.
PROVIDER = 'provider'

#: A dict containing credentials for various cloud providers in which the keys
#: can be any valid provider.  E.g.  ``aws``, ``hpcloud``.
DEPLOYER_CREDS = 'deployer_credentials'

#: The top-level key for logging-related configuration options.
LOGGING = 'logging'

#: Like chicken fried chicken... this is a way to configure the name of the tag
#: in which the combined stack-role (a.k.a. *name*) will be stored.  By
#: default, unless this is specified directly in ~/.bangrc, the *name* value
#: will be assigned to a tag named "Name" (this is the default tag displayed
#: in the AWS management console).  I.e. using Bang defaults, the server
#: named "bar" in the stack named "foo" will have the following tags::
#:
#:     stack:  foo
#:     role:   bar
#:     Name:   foo-bar
#:
#: In some cases, admins may have other purposes for the "Name" tag.  If
#: ~/.bangrc were to have ``name_tag_name`` set to ``descriptor``, then the
#: server described above would have the following tags::
#:
#:     stack:       foo
#:     role:        bar
#:     descriptor:  foo-bar
#:
#: To prevent Bang from assigning the *name* value to a tag, assign an empty
#: string to the ``name_tag_name`` attribute in ~/.bangrc.
NAME_TAG_NAME = 'name_tag_name'

#: This is a *derived* attribute that Bang provides for instance tagging, and
#: for Ansible playbooks to consume.  It's a combination of the :attr:`NAME`
#: and the :attr:`VERSION`.
STACK = 'stack'

KEY = 'key'

#: This is a *derived* attribute that Bang provides for instance tagging, and
#: for Ansible playbooks to consume.  It's a combination of the :attr:`NAME`
#: and the :attr:`VERSION`.
SERVER_CLASS = 'server_class'
