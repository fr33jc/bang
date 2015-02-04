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
import bang
import os
import getpass
import sys
from textwrap import dedent
from bang import attributes as A
from bang.stack import Stack
from bang.config import Config
from bang.util import get_argparser, initialize_logging


DEFAULT_SSH_USER = getpass.getuser()


def get_env_configs():
    raw_env_cfgs = os.environ.get('BANG_CONFIGS')
    if not raw_env_cfgs:
        return []
    return raw_env_cfgs.split(os.pathsep)


def set_ssh_creds(config, args):
    """
    Set ssh credentials into config.

    Note that these values might also be set in ~/.bangrc.  If they are
    specified both in ~/.bangrc and as command-line arguments to ``bang``, then
    the command-line arguments win.

    """
    creds = config.get(A.DEPLOYER_CREDS, {})
    creds[A.creds.SSH_USER] = args.user if args.user else creds.get(
            A.creds.SSH_USER,
            DEFAULT_SSH_USER,
            )
    if args.ask_pass:
        creds[A.creds.SSH_PASS] = getpass.getpass('SSH Password: ')
    config[A.DEPLOYER_CREDS] = creds


# note: this is its own function to allow documentation via sphinx-argparse
def get_parser():
    return get_argparser({
        'description': dedent("""\
            Deploys a full server stack based on a stack configuration file.

            In order to SSH into remote servers, ``bang`` needs the
            corresponding private key for the public key specified in the
            ``ssh_key_name`` fields of the config file.  This is easily managed
            with ssh-agent, so ``bang`` does not provide any ssh key management
            features.

            """),
        'arguments': [
            ('config_specs', {
                'help': dedent("""\
                    Stack config specs(s).

                    A *config spec* can either be a basename of a config file
                    (e.g.  ``mynewstack``), or a path to a config file (e.g.
                    ``../bang-stacks/mynewstack.yml``).

                    A basename is resolved into a proper path this way:

                        - Append ``.yml`` to the given name.
                        - Search the ``config_dir`` path for the resulting
                          filename, where the value for ``config_dir`` comes
                          from ``$HOME/.bangrc``.

                    When multiple config specs are supplied, the attributes
                    from all of the configs are deep-merged together into a
                    single, *union* config in the order specified in the
                    argument list.

                    If there are collisions in attribute names between separate
                    config files, the attributes in later files override those
                    in earlier files.

                    At deploy time, this can be used to provide secrets (e.g.
                    API keys, SSL certs, etc...) that you don't normally want
                    to check in to version control with the main stack
                    configuration.

                    """),
                'nargs': '*',
                'metavar': 'CONFIG_SPEC',
                }),
            ('--ask-pass', '-k', {
                'action': 'store_true',
                'help': 'ask for SSH password',
                }),
            ('--user', '-u', {
                'help': 'set SSH username (default=%s)' % DEFAULT_SSH_USER,
                }),
            ('--dump-config', {
                'choices': ['json', 'yaml', 'yml'],
                'help': 'Dump the merged config in the given format, then quit'
                }),
            ('--list', {
                'action': 'store_true',
                'help': dedent("""\
                        Dump stack inventory in ansible-compatible JSON.

                        Be sure to set the ``BANG_CONFIGS`` environment
                        variable to a colon-separated list of config specs.

                        E.g.

                            # specify the configs to use
                            export BANG_CONFIGS=/path/to/mystack.yml:/path/to/secrets.yml

                            # dump the inventory to stdout
                            bang --list

                            # run some command
                            ansible webservers -i /path/to/bang -m ping

                        """),
                'dest': 'ansible_list',
                }),
            ('--no-configure', {
                'action': 'store_false',
                'dest': 'configure',
                'help': dedent("""\
                        Do *not* configure the servers (i.e. do *not* run the
                        ansible playbooks).

                        This allows the person performing the deployment to
                        perform some manual tweaking between resource
                        deployment and server configuration.

                        """),
                }),
            ('--no-deploy', {
                'action': 'store_false',
                'dest': 'deploy',
                'help': dedent("""\
                        Do *not* deploy infrastructure resources.

                        This allows the person performing the deployment to
                        skip creating infrastructure and go straight to
                        configuring the servers.  It should be obvious that
                        configuration may fail if it references infrastructure
                        resources that have not already been created.

                        """),
                }),
            # TODO: implement validate/dry-run
            # ('--check', '-c', {
            #     'action': 'store_true',
            #     'help': 'Run sanity check on environment after deploying',
            #     }),
            # TODO: implement tag_stack
            ('--version', '-v', {
                'action': 'version',
                'version': '%%(prog)s %s' % bang.VERSION,
                }),
            ],
        })


def run_bang(alt_args=None):
    """
    Runs bang with optional list of strings as command line options.

    If ``alt_args`` is not specified, defaults to parsing ``sys.argv`` for
    command line options.
    """
    parser = get_parser()
    args = parser.parse_args(alt_args)

    source = args.config_specs or get_env_configs()
    if not source:
        return

    config = Config.from_config_specs(source)

    if args.dump_config:

        if args.dump_config in ('yaml', 'yml'):
            import yaml
            print yaml.safe_dump(dict(config))
        elif args.dump_config == 'json':
            import json
            print json.dumps(config)
        else:
            print config
        sys.exit()

    set_ssh_creds(config, args)

    stack = Stack(config)

    if args.ansible_list:
        stack.show_inventory()
        return

    initialize_logging(config)
    # TODO:  config.validate()
    if args.deploy:
        stack.deploy()
    if args.configure:
        stack.configure()
    config.autoinc()
