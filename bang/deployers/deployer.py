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
from collections import Callable
from ..util import log
from .. import BangError


class Deployer(object):
    """Base class for all deployers"""
    def __init__(self, stack, config):
        self.stack = stack
        self.phases = []
        self.inventory_phases = []

        # TODO: in retrospect, embedding config vals as attributes of Deployer
        # objects is not as flexible as i intended.  consider just storing it
        # as self.config.  should allow ServerDeployer.create() to handle
        # variations in provider's create_server() details without needing
        # things like CloudManagerServerDeployer.
        for k, v in config.iteritems():
            if '-' in k or ' ' in k:
                raise BangError(
                        'No hyphens or spaces in config key names please! %s'
                        % k
                        )
            self.__dict__[k] = v

    def deploy(self):
        for should_run, action in self.phases:
            if isinstance(should_run, Callable):
                if should_run():
                    action()
            elif should_run:
                action()

    def inventory(self):
        """
        Gathers ansible inventory data.

        Looks for existing servers that are members of the stack.

        Does not attempt to *create* any resources.
        """
        for action in self.inventory_phases:
            action()

    def run(self, action):
        """
        Runs through the phases defined by :attr:`action`.

        :param str action:  Either ``deploy`` or ``inventory``.

        """
        deployer = self.__class__.__name__
        log.info('Running %s...' % deployer)
        try:
            if action == 'deploy':
                self.deploy()
            elif action == 'inventory':
                self.inventory()
        except BangError as e:
            log.error(e.message)
            raise
        log.info('%s complete.' % deployer)
