import os.path
import yaml
import bang.providers.rs as RS
from nose.plugins.attrib import attr


RC_FILE = os.path.expanduser('~/.bangrc')


@attr('rc_creds', 'real_conn')
def test_find_servers():
    with open(RC_FILE) as f:
        rcdata = yaml.load(f)
    creds = rcdata['deployer_credentials']['rightscale']
    provider = RS.RightScale(creds)
    servers = provider.get_consul('servers')


def test_normalize_input_values():
    values = (
            ('blank', 'blank'),
            ('ignore', 'ignore'),
            ('inherit', 'inherit'),
            ('text:foo', 'text:foo'),
            ('env:foo', 'env:foo'),
            ('cred:foo', 'cred:foo'),
            ('key:foo', 'key:foo'),
            ('key:foo:1', 'key:foo:1'),
            ('array:foo', 'array:foo'),
            ('bar', 'text:bar'),
            ('unknown:blah', 'text:unknown:blah'),
            ('unknown:blah', 'text:unknown:blah'),
            ('78:31:c1:ce:73:86', 'text:78:31:c1:ce:73:86'),
            )
    for gozinta, gozoutta in values:
        assert gozoutta == RS.normalize_input_value(gozinta)
