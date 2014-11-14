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
import bang.config as C
import copy
import os
import os.path
import shutil
import tempfile
import textwrap
import unittest
import yaml

from mock import patch
from bang import attributes as A


class TestWithTmpDir(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.mkdtemp()
        self.tmpdir = tmpdir
        self.bangrc = os.path.join(tmpdir, '.bangrc')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _store_bangrc(self, data):
        with open(self.bangrc, 'w') as f:
            f.write(textwrap.dedent(data))


class TestBangrc(TestWithTmpDir):

    def _parse_bangrc(self):
        with patch.dict('os.environ', {'HOME': self.tmpdir}):
            return C.parse_bangrc()

    def test_creds_from_bangrc(self):
        aws_id = 'AKIAIKFIE8FKSLR8FIE3'
        aws_secret = 'EU859vjksor73gkY378f9gkslbkrabcxwfyW2loo'
        hp_u = 'whazup'
        hp_p = 'iseeparisiseefrance'
        exp = {
                'deployer_credentials': {
                    'aws': {
                        'access_key_id': aws_id,
                        'secret_access_key': aws_secret,
                        },
                    'hpcloud': {
                        'username': hp_u,
                        'password': hp_p,
                        },
                    },
                }
        self._store_bangrc('''\
                deployer_credentials:
                  aws:
                    access_key_id: %(aws_id)s
                    secret_access_key: %(aws_secret)s
                  hpcloud:
                    username: %(hp_u)s
                    password: %(hp_p)s
                ''' % locals()
                )
        act = self._parse_bangrc()
        self.assertEqual(exp, act)

    def test_non_existent(self):
        self.assertEqual({}, self._parse_bangrc())

    def test_only_rc_keys(self):
        self._store_bangrc(
                '\n'.join('%s: []' % k for k in C.ALL_RESERVED_KEYS)
                )
        exp = dict((k, []) for k in C.RC_KEYS)
        act = self._parse_bangrc()
        self.assertEqual(exp, act)

    def test_non_mapping(self):
        self._store_bangrc('[foo, bar, deployer_credentials]')
        self.assertRaises(TypeError, self._parse_bangrc)


class TestConfigSpec(unittest.TestCase):

    def test_path(self):
        # gozinta == gozoutta
        for exp in (
                '/home/deployer/bang-stacks/fubar.yml',
                '../blargh/asdf.yml',
                './testcfg',
                'stacks/buya.yml',
                'buya.yml',
                ):
            act = C.resolve_config_spec(exp)
            self.assertEqual(exp, act)

        # transformation
        for args, exp in (
                (('foo', ), 'foo.yml'),
                (('foo', '/path/to/configs'), '/path/to/configs/foo.yml'),
                (('bar', '/path/to/configs/'), '/path/to/configs/bar.yml'),
                (('fullstack', '/etc/bang'), '/etc/bang/fullstack.yml'),
                ):
            act = C.resolve_config_spec(*args)
            self.assertEqual(exp, act)

    def test_basename(self):
        stacks_dir = '/home/deployer/bang-stacks'
        name = 'fubar'
        exp = '%s/%s.yml' % (stacks_dir, name)
        act = C.resolve_config_spec(name, stacks_dir)
        self.assertEqual(exp, act)


class TestConfig(TestWithTmpDir):
    a = {
            'a': 1,
            'b': 2,
            'c': 3,
            'd': {
                'd1': 'one',
                'd2': 'two',
                'd3': 'three',
                },
            'e': {
                'eA': 'ay',
                'eB': {
                    'eB1': 'uno',
                    'eB2': 'dos',
                    'eB3': {
                        'eB3a': 'ah',
                        'eB3b': 'bay',
                        'eB3f': 'same',
                        },
                    },
                }
            }

    b = {
            'c': 42,
            'd': {
                'd1': 'new',
                'd3': ['replace', 'the', 'scalar'],
                'd4': 4,
                },
            'e': {
                'eB': {
                    'eB3': {
                        'eB3a': 'alpha',
                        'eB3e': 'echo',
                        'eB3f': 'same',
                        },
                    },
                },
            'z': 26,
            }

    a_b_merged = {
            'a': 1,
            'b': 2,
            'c': 42,
            'd': {
                'd1': 'new',
                'd2': 'two',
                'd3': ['replace', 'the', 'scalar'],
                'd4': 4,
                },
            'e': {
                'eA': 'ay',
                'eB': {
                    'eB1': 'uno',
                    'eB2': 'dos',
                    'eB3': {
                        'eB3a': 'alpha',
                        'eB3b': 'bay',
                        'eB3e': 'echo',
                        'eB3f': 'same',
                        },
                    },
                },
            'z': 26,
            }

    def setUp(self):
        super(TestConfig, self).setUp()
        config_dir = os.path.join(self.tmpdir, 'bang-stacks')
        os.mkdir(config_dir, 0700)
        self.config_dir = config_dir

    def _store_config(self, fname, cfg_dict):
        raw = yaml.dump(cfg_dict, default_flow_style=False)
        raw_path = os.path.join(self.config_dir, fname)
        with open(raw_path, 'w') as f:
            f.write(raw)
        return raw_path

    def _get_act_config(self, cfg_specs):
        with patch.dict('os.environ', {'HOME': self.tmpdir}):
            return C.Config.from_config_specs(cfg_specs, prepare=False)

    def test_no_config_specs(self):
        # first with no bangrc
        act = self._get_act_config([])
        self.assertEqual({}, act)

        # then, with a bangrc
        bangrc = dict(zip(C.RC_KEYS, ('foo', 'bar')))
        self._store_bangrc(yaml.dump(bangrc))
        act = self._get_act_config([])
        self.assertEqual(bangrc, act)

    def test_all_in_one_yaml(self):
        exp = {
                'name': 'mystack',
                'version': '42.0',
                'playbooks': [
                    'foo.yml',
                    'bar.yml',
                    ],
                'servers': [
                    {
                        'groups': ['webservers', 'myapp'],
                        'provider': 'hpcloud',
                        'instance_type': 'standard.medium',
                        'os_image_id': '48005',
                        'instance_count': 2,
                        'config_scopes': ['myapp'],
                        },
                    ],
                'myapp': {
                    'attr1': 'val1',
                    'attr2': 'val2',
                    },
                }
        raw_path = self._store_config('mystack.yml', exp)
        act = self._get_act_config([raw_path])
        self.assertEqual(exp, act)

    def test_two_yamls(self):
        exp = self.a_b_merged
        a_path = self._store_config('a.yml', self.a)
        b_path = self._store_config('b.yml', self.b)
        act = self._get_act_config([a_path, b_path])
        self.assertEqual(exp, act)

    def test_two_yamls_and_a_bangrc_walk_into_a_bar(self):
        rcdata = {
                # just make sure keys at this level do *not* intersect with
                # top-level keys in self._a_b_merged
                'deployer_credentials': {
                    'aws': {
                        'access_key_id': 'AKIAIKFIE8FKSLR8FIE3',
                        'secret_access_key':
                                'EU859vjksor73gkY378f9gkslbkrabcxwfyW2loo',
                        },
                    'hpcloud': {
                        'username': 'whazup',
                        'password': 'iseeparisiseefrance',
                        },
                    },
                }
        self._store_bangrc(yaml.dump(rcdata))
        exp = copy.deepcopy(self.a_b_merged)
        exp.update(rcdata)
        a_path = self._store_config('a.yml', self.a)
        b_path = self._store_config('b.yml', self.b)
        act = self._get_act_config([a_path, b_path])
        self.assertEqual(exp, act)

    def test_basename_specs(self):
        name = 'fubar'
        self._store_config('%s.yml' % name, self.a)
        orig_dir = os.getcwd()
        os.chdir(self.tmpdir)
        cfg = self._get_act_config([name])
        exp_path = '%s/%s.yml' % (C.DEFAULT_CONFIG_DIR, name)
        self.assertEqual(exp_path, cfg.filepath)
        self.assertEqual(self.a, cfg)
        os.chdir(orig_dir)


@patch('bang.config.ask_passwords')
def test_prompt_vault_pass(mock_ask_passwords):
    exp_vault_pass = 'vaultpass'
    mock_ask_passwords.return_value = (
            'sshpass',
            'sudopass',
            'supass',
            exp_vault_pass,
            )

    # happy path
    config = C.Config({
        A.ANSIBLE: {A.ansible.ASK_VAULT_PASS: True}
        })
    config._prepare_ansible()
    assert mock_ask_passwords.called

    # prompted should override a value set in a config file
    mock_ask_passwords.reset_mock()
    config = C.Config({
        A.ANSIBLE: {
            A.ansible.ASK_VAULT_PASS: True,
            A.ansible.VAULT_PASS: 'default_vault_pass',
            }
        })
    config._prepare_ansible()
    assert exp_vault_pass == config[A.ANSIBLE][A.ansible.VAULT_PASS]

    # all default cases should *not* prompt for password
    # ... explicitly set False
    mock_ask_passwords.reset_mock()
    config = C.Config({
        A.ANSIBLE: {A.ansible.ASK_VAULT_PASS: False}
        })
    config._prepare_ansible()
    assert not mock_ask_passwords.called

    # ... no ask_vault_pass config
    mock_ask_passwords.reset_mock()
    config = C.Config({A.ANSIBLE: {}})
    config._prepare_ansible()
    assert not mock_ask_passwords.called

    # ... no ansible configs at all
    mock_ask_passwords.reset_mock()
    config = C.Config()
    config._prepare_ansible()
    assert not mock_ask_passwords.called
