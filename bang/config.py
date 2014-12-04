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
import collections
import os
import os.path
import tempfile
import yaml

from . import resources as R, attributes as A
from .util import log, bump_version_tail, deep_merge_dicts
from ansible.utils import ask_passwords


DEFAULT_CONFIG_DIR = 'bang-stacks'
DEFAULT_LAUNCH_TIMEOUT_S = 0

RC_KEYS = [
        A.DEPLOYER_CREDS,
        'config_dir',
        A.NAME_TAG_NAME,
        A.LOGGING,
        A.ANSIBLE,
        ]

ALL_RESERVED_KEYS = RC_KEYS + R.DYNAMIC_RESOURCE_KEYS


def find_component_tarball(bucket, comp_name, comp_config):
    """
    Returns True if the component tarball is found in the bucket.

    Otherwise, returns False.
    """
    values = {
            'name': comp_name,
            'version': comp_config['version'],
            'platform': comp_config['platform'],
            }
    template = comp_config.get('archive_template')
    if template:
        key_name = template % values
    else:
        key_name = '%(name)s/%(name)s-%(version)s.tar.gz' % values
    if not bucket.get_key(key_name):
        log.error('%s not found' % key_name)
        return False
    return True


def read_raw_bangrc():
    try:
        # the path creation is in the try/except because $HOME might not exist
        # in the current environ (e.g. init scripts)
        bangrc_path = os.path.join(os.environ['HOME'], '.bangrc')
        with open(bangrc_path) as f:
            return yaml.safe_load(f)
    except:
        return {}


def parse_bangrc():
    """
    Parses ``$HOME/.bangrc`` for global settings and deployer credentials.  The
    ``.bangrc`` file is expected to be a YAML file whose outermost structure is
    a key-value map.

    Note that even though ``.bangrc`` is just a YAML file in which a user could
    store any top-level keys, it is not expected to be used as a holder of
    default values for stack-specific configuration attributes - if present,
    they will be ignored.

    Returns {} if ``$HOME/.bangrc`` does not exist.

    :rtype:  :class:`dict`

    """
    raw = read_raw_bangrc()
    return dict((k, raw[k]) for k in raw if k in RC_KEYS)


def resolve_config_spec(config_spec, config_dir=''):
    """
    Resolves :attr:`config_spec` to a path to a config file.

    :param str config_spec:  Valid config specs:

        - The basename of a YAML config file *without* the ``.yml`` extension.
          The full path to the config file is resolved by appending ``.yml`` to
          the basename, then by searching for the result in the
          :attr:`config_dir`.

        - The path to a YAML config file.  The path may be absolute or may be
          relative to the current working directory.  If :attr:`config_spec`
          contains a ``/`` (forward slash), or if it ends in ``.yml``, it is
          treated as a path.

    :param str config_dir:  The directory in which to search for stack
        configuration files.

    :rtype:  :class:`str`

    """
    if '/' in config_spec or config_spec.endswith('.yml'):
        return config_spec
    return os.path.join(config_dir, '%s.yml' % config_spec)


class Config(dict):
    """
    A dict-alike that provides a convenient constructor, stashes the path
    to the config file as an instance attribute, and performs some validation
    of the values.
    """
    def __init__(self, *args, **kwargs):
        """

        :param str path_to_yaml:  Path to a yaml file to use as the data source
            for the returned instance.

        """
        super(Config, self).__init__(*args, **kwargs)
        self.filepath = ''

    @classmethod
    def from_config_specs(cls, config_specs, prepare=True):
        """
        Alternate constructor that merges config attributes from
        ``$HOME/.bangrc`` and :attr:`config_specs` into a single
        :class:`Config` object.

        The first (and potentially *only* spec) in :attr:`config_specs` should
        be main configuration file for the stack to be deployed.  The returned
        object's :attr:`filepath` will be set to the absolute path of the first
        config file.

        If multiple config specs are supplied, their values are merged together
        in the order specified in :attr:`config_specs` - That is, later values
        override earlier values.

        :param config_specs:  List of config specs.
        :type config_specs:  :class:`list` of :class:`str`

        :param bool prepare:  Flag to control whether or not :meth:`prepare` is
            called automatically before returning the object.

        :rtype:  :class:`Config`

        """
        bangrc = parse_bangrc()
        config_dir = bangrc.get('config_dir', DEFAULT_CONFIG_DIR)
        config_paths = [
                resolve_config_spec(cs, config_dir) for cs in config_specs
                ]
        config = cls()
        config.update(bangrc)
        if config_paths:
            config.filepath = config_paths[0]
        for c in config_paths:
            with open(c) as f:
                deep_merge_dicts(config, yaml.safe_load(f))
        if prepare:
            config.prepare()
        return config

    def _prepare_ansible(self):
        ansible_cfg = self.get(A.ANSIBLE, {})
        if ansible_cfg.get(A.ansible.ASK_VAULT_PASS):
            (_, _, _, vault_pass) = ask_passwords(ask_vault_pass=True)
            ansible_cfg[A.ansible.VAULT_PASS] = vault_pass
            self[A.ANSIBLE] = ansible_cfg

    def _prepare_dbs(self):
        dbcreds = self.get(R.DATABASE_CREDS, {})
        for db in self.get(R.DATABASES, []):
            name = db[A.database.NAME]

            # default db name is the deployer instance name
            if A.database.DB_NAME not in db:
                db[A.database.DB_NAME] = name
            if A.database.LAUNCH_TIMEOUT not in db:
                db[A.database.LAUNCH_TIMEOUT] = DEFAULT_LAUNCH_TIMEOUT_S

            # make global db creds available to db deployer instance
            creds = dbcreds.get(name)
            if not creds:
                continue
            db[A.database.ADMIN_USER] = creds[A.database.ADMIN_USER]
            db[A.database.ADMIN_PASS] = creds[A.database.ADMIN_PASS]

    def _prepare_secgroups(self):
        stack = self[A.NAME]
        # Special magic groups for lb
        load_balancer_groups = []
        for lb in self.get(R.LOAD_BALANCERS, []):
            for_servers = lb[A.loadbalancer.SERVER_NAMES]
            for_server = filter(
                    lambda s: s[A.server.NAME] == for_servers,
                    self[R.SERVERS])[0]
            secgroup_name = '%s-secgroup' % lb[A.loadbalancer.NAME]
            sec_group = {
                A.secgroup.NAME: secgroup_name,
                A.secgroup.PROVIDER: for_server[A.server.PROVIDER],
                A.secgroup.REGION: for_server[A.server.REGION],
                'description': "Secgroup for %s load balancer" % lb[A.loadbalancer.NAME],
                A.secgroup.RULES: [],
                'load_balancer': lb[A.loadbalancer.NAME],
            }

            load_balancer_groups.append(sec_group)
            self.setdefault(R.DYNAMIC_LB_SEC_GROUPS, []).append(sec_group)
            for_server.setdefault(A.server.STACK_SECGROUPS, []).append(secgroup_name)

        sg_rule_sets = []
        self.setdefault(R.SERVER_SECURITY_GROUPS, []).extend(load_balancer_groups)
        for sg in self.get(R.SERVER_SECURITY_GROUPS, []):
            provider = sg[A.secgroup.PROVIDER]
            region = sg[A.secgroup.REGION]
            # dress up the stack secgroup names
            dressy_name = '%s-%s' % (stack, sg[A.secgroup.NAME])
            sg[A.secgroup.NAME] = dressy_name
            rules = []
            for rule in sg[A.secgroup.RULES]:
                r = rule.copy()

                # handle special sources
                if rule.get(A.secgroup.SOURCE_SELF):
                    r[A.secgroup.SOURCE] = dressy_name
                elif rule.get(A.secgroup.SOURCE_STACK):
                    r[A.secgroup.SOURCE] = '%s-%s' % (
                            stack, rule[A.secgroup.SOURCE])

                r[A.secgroup.TARGET] = dressy_name
                rules.append(r)

            # For load balancer SGs, don't add rule sets now;
            # it'll get done later
            if not sg.get('load_balancer', None):
                sg_rule_sets.append(
                    {
                        A.secgroup.NAME: dressy_name,
                        A.secgroup.PROVIDER: provider,
                        A.secgroup.REGION: region,
                        A.secgroup.RULES: rules,
                        }
                    )
        self[R.SERVER_SECURITY_GROUP_RULES] = sg_rule_sets

        # make sure server configs use the dressed-up secgroup names
        for s in self.get(R.SERVERS, []):
            groups = [
                    '%s-%s' % (stack, gname)
                    for gname in s.get(A.server.STACK_SECGROUPS, [])
                    ]
            groups.extend(s.get(A.server.EXTRA_SECGROUPS, []))
            s[A.server.SECGROUPS] = groups

    def _prepare_tags(self):
        # add ``stack`` and ``role`` tags
        name_tag_name = self.get(A.NAME_TAG_NAME, 'Name')
        for s in self.get(R.SERVERS, []):
            stack = self[A.NAME]
            role = s[A.server.NAME]
            tags = s.get(A.server.TAGS, {})
            tags[A.tags.STACK] = stack
            tags[A.tags.ROLE] = role
            if name_tag_name:
                tags[name_tag_name] = '%s-%s' % (stack, role)
            s[A.server.TAGS] = tags

    def _prepare_ssh_keys(self):
        keys = self.get(A.DEPLOYER_CREDS, {}).get(R.SSH_KEYS, {})
        if not keys:
            return
        keys_to_install = []
        for server in self.get(R.SERVERS, []):
            key_name = server.get(A.server.SSH_KEY)
            if not key_name:
                continue
            key = keys.get(key_name)
            if not key:
                continue
            keys_to_install.append(
                    {
                        A.ssh_key.NAME: key_name,
                        A.ssh_key.KEY: key,
                        A.ssh_key.PROVIDER: server[A.server.PROVIDER],
                        A.ssh_key.REGION: server[A.server.REGION],
                        }
                    )
        if keys_to_install:
            self[R.SSH_KEYS] = keys_to_install

    def _prepare_servers(self):
        """
        Prepare the variables that are exposed to the servers.

        Most attributes in the server config are used directly.  However, due
        to variations in how cloud providers treat regions and availability
        zones, this method allows either the ``availability_zone`` or the
        ``region_name`` to be used as the target availability zone for a
        server.  If both are specified, then ``availability_zone`` is used.  If
        ``availability_zone`` is not specified in the server config, then the
        ``region_name`` value is used as the target availability zone.

        """
        stack = {
                A.NAME: self[A.NAME],
                A.VERSION: self[A.VERSION],
                }
        for server in self.get(R.SERVERS, []):
            # default cloud values
            if A.PROVIDER in server:
                if A.server.LAUNCH_TIMEOUT not in server:
                    server[A.server.LAUNCH_TIMEOUT] = DEFAULT_LAUNCH_TIMEOUT_S
                if A.server.POST_DELAY not in server:
                    server[A.server.POST_DELAY] = DEFAULT_LAUNCH_TIMEOUT_S
                if A.server.AZ not in server:
                    server[A.server.AZ] = server[A.server.REGION]

            # distribute the config scope attributes
            svars = {
                    A.STACK: stack,
                    A.SERVER_CLASS: server[A.NAME],
                    }
            for scope in server.get(A.server.SCOPES, []):
                # allow scopes to be defined inline
                if isinstance(scope, collections.Mapping):
                    svars.update(scope)
                else:
                    svars[scope] = self[scope]

            # make all of the launch-time attributes (e.g. disk_image_id,
            # launch_timeout_s, ssh_key_name, etc...) available as facts in
            # case you need them in a playbook.
            sattrs = server.copy()
            sattrs.pop(A.server.SCOPES, None)
            svars[A.server.BANG_ATTRS] = sattrs

            server[A.server.VARS] = svars

    def _prepare_load_balancers(self):
        """
        Prepare load balancer variables
        """
        stack = {
                A.NAME: self[A.NAME],
                A.VERSION: self[A.VERSION],
                }

        for load_balancer in self.get(R.LOAD_BALANCERS, []):
            svars = {A.STACK: stack}
            load_balancer[A.loadbalancer.VARS] = svars

    def _convert_to_list(self, stanza_key, name_key):
        """
        Convert self[stanza_key] to a list. For each k, v
        k, v = self[stanza_key].iteritems() assign
        v[name_key] = k
        """
        converted_list = []
        for k, v in self.get(stanza_key, {}).iteritems():
            v[name_key] = k
            converted_list.append(v)
        return converted_list

    def prepare(self):
        """
        Reorganizes the data such that the deployment logic can find it all
        where it expects to be.

        The raw configuration file is intended to be as human-friendly as
        possible partly through the following mechanisms:

            - In order to minimize repetition, any attributes that are common
              to all server configurations can be specified in the
              ``server_common_attributes`` stanza even though the stanza itself
              does not map directly to a deployable resource.
            - For reference locality, each security group stanza contains its
              list of rules even though rules are actually created in a
              separate stage from the groups themselves.

        In order to make the :class:`Config` object more useful to the program
        logic, this method performs the following transformations:

            - Distributes the ``server_common_attributes`` among all the
              members of the ``servers`` stanza.
            - Extracts security group rules to a top-level key, and
              interpolates all source and target values.

        """
        # TODO: take server_common_attributes and disperse it among the various
        # server stanzas

        # First stage - turn all the dicts (SERVER, SECGROUP, DATABASE, LOADBAL)
        # into lists now they're merged properly
        for stanza_key, name_key in (
                (R.SERVERS, A.server.NAME),
                (R.SERVER_SECURITY_GROUPS, A.secgroup.NAME),
                (R.LOAD_BALANCERS, A.loadbalancer.NAME),
                (R.DATABASES, A.database.NAME),
                (R.BUCKETS, A.NAME),
                (R.QUEUES, A.NAME)):
            self[stanza_key] = self._convert_to_list(stanza_key, name_key)

        self._prepare_ssh_keys()
        self._prepare_secgroups()
        self._prepare_tags()
        self._prepare_dbs()
        self._prepare_servers()
        self._prepare_load_balancers()
        self._prepare_ansible()

    def validate(self):
        """
        Performs all validation checks on this config.

        Raises :class:`ValueError` for invalid configs.

        """
        # TODO: validate providers in each of the resource stanzas

    def autoinc(self):
        """
        Conditionally updates the stack version in the file associated with
        this config.

        This  handles both official releases (i.e. QA configs), and release
        candidates.  Assumptions about version:

            - Official release versions are MAJOR.minor, where MAJOR and minor
              are both non-negative integers.  E.g.

                2.9
                2.10
                2.11
                3.0
                3.1
                3.2
                etc...

            - Release candidate versions are MAJOR.minor-rc.N, where MAJOR,
              minor, and N are all non-negative integers.

                3.5-rc.1
                3.5-rc.2

        """
        if not self.get('autoinc_version'):
            return

        oldver = self['version']
        newver = bump_version_tail(oldver)

        config_path = self.filepath
        temp_fd, temp_name = tempfile.mkstemp(
                dir=os.path.dirname(config_path),
                )
        with open(config_path) as old:
            with os.fdopen(temp_fd, 'w') as new:
                for oldline in old:
                    if oldline.startswith('version:'):
                        new.write("version: '%s'\n" % newver)
                        continue
                    new.write(oldline)

        # no need to backup the old file, it's under version control anyway -
        # right???
        log.info('Incrementing stack version %s -> %s' % (oldver, newver))
        os.rename(temp_name, config_path)
        # TODO: commit_bang_config()
