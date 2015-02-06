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
import copy
import functools
import json
import multiprocessing
import os.path

# work around circular import in ansible as discussed on ansible-devel:
#
#     https://groups.google.com/forum/#!topic/ansible-devel/wE7fNbGyWbo
#
import ansible.utils  # noqa

from ansible import callbacks
from ansible.playbook import PlayBook
from .deployers import get_stage_deployers
from .inventory import BangsibleInventory
from .util import log, SharedNamespace, SharedMap
from . import BangError, resources as R, attributes as A


def require_inventory(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        if not self.have_inventory:
            self.gather_inventory()
        return f(self, *args, **kwargs)
    return wrapper


class Stack(object):
    """
    Deploys infrastructure/platform resources, then configures any deployed
    servers using ansible playbooks.

    """
    def __init__(self, config):
        """
        :param config:  A mapping object with configuration keys and values.
            May be arbitrarily nested.
        :type config:  :class:`bang.config.Config`

        """
        self.name = config[A.NAME]
        self.version = config[A.VERSION]
        self.config = config
        self.manager = multiprocessing.Manager()
        self.shared_namespaces = {}

        self.groups_and_vars = SharedMap(self.manager)
        self.lb_sec_groups = SharedMap(self.manager)
        self.have_inventory = False

        """
        Deployers stash inventory data for any newly-created servers in this
        mapping object.  Note: uses SharedMap because this must be
        multiprocess-safe.

        """

        # TODO: suss out autoscaling. see count_to_deploy()

    def get_deployers(self):
        """
        Returns a :class:`list` of *stages*, where each *stage* is a
        :class:`list` of :class:`~bang.deployers.deployer.Deployer` objects.
        It defines the execution order of the various deployers.

        """
        return enumerate(
                [get_stage_deployers(keys, self) for keys in R.STAGES]
                )

    def get_namespace(self, key):
        """
        Returns a :class:`~bang.util.SharedNamespace` for the given
        :attr:`key`.  These are used by
        :class:`~bang.deployers.deployer.Deployer` objects of the same
        ``deployer_class`` to coordinate control over multiple deployed
        instances of like resources.  E.g. With 5 clones of an application
        server, 5 :class:`~bang.deployers.deployer.Deployer` objects in
        separate, concurrent processes will use the same shared namespace to
        ensure that each object/process controls a distinct server.

        :param str key:  Unique ID for the
            namespace.  :class:`~bang.deployers.deployer.Deployer` objects that
            call :meth:`get_namespace` with the same :attr:`key` will receive
            the same :class:`~bang.util.SharedNamespace` object.

        """
        namespace = self.shared_namespaces.get(key)
        if namespace:
            return namespace
        ns = SharedNamespace(self.manager)
        self.shared_namespaces[key] = ns
        return ns

    def find_first(self, attr_name, resources, extra_prefix=''):
        """
        Returns the boto object for the first resource in ``resources`` that
        belongs to this stack.  Uses the attribute specified by ``attr_name``
        to match the stack name.

        E.g.  An RDS instance for a stack named ``foo`` might be named
        ``foo-mydb-fis8932ifs``.  This call::

            find_first('id', conn.get_all_dbinstances())

        would return the boto.rds.dbinstance.DBInstance object whose ``id`` is
        ``foo-mydb-fis8932ifs``.

        Returns None if a matching resource is not found.

        If specified, ``extra_prefix`` is appended to the stack name prefix
        before matching.
        """
        prefix = self.name + '-' + (extra_prefix + '-' if extra_prefix else '')
        for res in resources:
            attr = getattr(res, attr_name)
            if attr.startswith(prefix):
                return res

    def add_lb_secgroup(self, lb_name, hosts, port):
        """
        Used by the load balancer deployer to register a hostname
        for a load balancer, in order that security group rules can be
        applied later. This is multiprocess-safe, but since keys are
        accessed only be a single load balancer deployer there should be
        no conflicts.

        :param str lb_name: The load balancer name (as per the config file)

        :param :class:`list` hosts:  The load balancer host[s], once known

        :param port:  The backend port that the LB will connect on
        """
        self.lb_sec_groups.merge(lb_name, {'hosts': hosts, 'port': port})

    def add_host(self, host, group_names=None, host_vars=None):
        """
        Used by deployers to add hosts to the inventory.

        :param str host:  The host identifier (e.g. hostname, IP address) to
            use in the inventory.

        :param list group_names:  A list of group names to which the host
            belongs.  **Note:  This list will be sorted in-place.**

        :param dict host_vars:  A mapping object of host *variables*.  This can
            be a nested structure, and is used as the source of all the
            variables provided to the ansible playbooks.  **Note:  Additional
            key-value pairs (e.g. dynamic ansible values like
            ``inventory_hostname``) will be inserted into this mapping
            object.**

        """
        gnames = group_names if group_names else []
        hvars = host_vars if host_vars else {}

        # Add in ansible's magic variables.  Assign them here because this is
        # just about the earliest point we can calculate them before anything
        # ansible-related (e.g. Stack.configure(), ``bang --host``) executes.
        gnames.sort()
        hvars[A.server.GROUP_NAMES] = gnames
        hvars[A.server.INV_NAME] = host
        hvars[A.server.INV_NAME_SHORT] = host.split('.')[0]

        self.groups_and_vars.merge(host, hvars)

        for gname in group_names:
            self.groups_and_vars.append(gname, host)

    def describe(self):
        """Iterates through the deployers but doesn't run anything"""
        for stage, corunners in self.get_deployers():
            print self.name, "STAGE ", stage
            for d in corunners:
                print d.__class__.__name__, ",".join(
                        [p[1].__name__ for p in d.phases]
                        )

    def _run(self, action):
        for stage, corunners in self.get_deployers():
            children = []
            errors = 0
            for d in corunners:
                p = multiprocessing.Process(
                        name=d.__class__.__name__,
                        target=d.run,
                        args=(action, ),
                        )
                children.append(p)
                p.start()
            for child in children:
                child.join()
                if child.exitcode != 0:
                    errors += 1
            if errors:
                msg = "Stage %d had %d errors." % (stage, errors)
                log.error(msg)
                raise BangError(msg)

    def deploy(self):
        """
        Iterates through the deployers returned by ``self.get_deployers()``.

        Deployers in the same stage are run concurrently.  The runner only
        proceeds to the next stage once all of the deployers in the same
        stage have completed successfully.

        Any failures in a stage cause the run to terminate before proceeding to
        the next stage.

        """
        self._run('deploy')
        self.have_inventory = True

    @require_inventory
    def configure(self):
        """
        Executes the ansible playbooks that configure the servers in the stack.

        Assumes that the root playbook directory is ``./playbooks/`` relative
        to the stack configuration file.  Also sets the ansible *module_path*
        to be ``./common_modules/`` relative to the stack configuration file.

        E.g.  If the stack configuration file is::

            $HOME/bang-stacks/my_web_service.yml

        then the root playbook directory is::

            $HOME/bang-stacks/playbooks/

        and the ansible module path is::

            $HOME/bang-stacks/common_modules/

        """
        cfg = self.config
        bang_config_dir = os.path.abspath(
                os.path.dirname(cfg.filepath)
                )
        playbook_dir = os.path.join(bang_config_dir, 'playbooks')
        creds = cfg.get(A.DEPLOYER_CREDS, {})
        pb_kwargs = {
                # this allows connection reuse using "ControlPersist":
                'transport': 'ssh',
                'module_path': os.path.join(bang_config_dir, 'common_modules'),
                'remote_pass': creds.get(A.creds.SSH_PASS),
                # TODO: determine forks
                # 'forks': options.forks,
                }
        # only add the 'remote_user' kwarg if it's in the config, otherwise use
        # ansible's default behaviour.
        ssh_user = creds.get(A.creds.SSH_USER)
        if ssh_user:
            pb_kwargs['remote_user'] = ssh_user

        ansible_cfg = cfg.get(A.ANSIBLE, {})
        ansible_verbosity = ansible_cfg.get(A.ansible.VERBOSITY, 1)
        ansible.utils.VERBOSITY = ansible_verbosity
        for playbook in cfg.get(A.PLAYBOOKS, []):
            playbook_path = os.path.join(playbook_dir, playbook)

            # gratuitously stolen from main() in ``ansible-playbook``
            stats = callbacks.AggregateStats()
            playbook_cb = callbacks.PlaybookCallbacks(
                    verbose=ansible_verbosity
                    )
            runner_cb = callbacks.PlaybookRunnerCallbacks(
                    stats,
                    verbose=ansible_verbosity
                    )

            extra_kwargs = {
                    'playbook': playbook_path,

                    # TODO: do we really need new instances of the following
                    # for each playbook?
                    'callbacks': playbook_cb,
                    'runner_callbacks': runner_cb,
                    'stats': stats,

                    # ``host_list`` is used to generate the inventory, but
                    # don't worry, we override the inventory later
                    'host_list': [],
                    'vault_password': ansible_cfg.get(A.ansible.VAULT_PASS),
                    }
            pb_kwargs.update(extra_kwargs)
            pb = PlayBook(**pb_kwargs)
            inventory = BangsibleInventory(
                    copy.deepcopy(self.groups_and_vars.lists),
                    copy.deepcopy(self.groups_and_vars.dicts),
                    )
            inventory.set_playbook_basedir(playbook_dir)
            pb.inventory = inventory

            pb.run()

            hosts = sorted(pb.stats.processed.keys())
            playbook_cb.on_stats(pb.stats)

            failed = False
            for h in hosts:
                hsum = pb.stats.summarize(h)
                if hsum['failures'] or hsum['unreachable']:
                    failed = True
                print "%-30s : %s" % (h, hsum)
                # TODO: sort this out
                # print "%-30s : %s %s %s %s " % (
                #     hostcolor(h, hsum),
                #     colorize('ok', hsum['ok'], 'green'),
                #     colorize('changed', hsum['changed'], 'yellow'),
                #     colorize('unreachable', hsum['unreachable'], 'red'),
                #     colorize('failed', hsum['failures'], 'red'))

            if failed:
                raise BangError("Server configuration failed!")

    def gather_inventory(self):
        """
        Gathers existing inventory info.

        Does *not* create any new infrastructure.
        """
        self._run('inventory')
        self.have_inventory = True

    @require_inventory
    def show_inventory(self):
        """
        Satisfies the ``--list`` portion of ansible's external inventory API.

        Allows ``bang`` to be used as an external inventory script, for example
        when running ad-hoc ops tasks.  For more details, see:
        http://ansible.cc/docs/api.html#external-inventory-scripts

        """
        inv_lists = copy.deepcopy(self.groups_and_vars.lists)
        # sort the host lists to help consumers of the inventory (e.g. ansible
        # playbooks)
        for l in inv_lists.values():
            l.sort()

        # new in ansible 1.3: add hostvars directly into ``--list`` output
        inv_lists['_meta'] = {
                'hostvars': self.groups_and_vars.dicts.copy()
                }

        print json.dumps(inv_lists)
