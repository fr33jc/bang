import rightscale

from .. import resources as R, attributes as A
from .bases import Provider, Consul
from rightscale.util import find_by_name


def server_to_dict(server):
    """
    Returns the :class:`dict` representation of a server object.

    The returned :class:`dict` is meant to be consumed by
    :class:`~bang.deployers.cloud.ServerDeployer` objects.

    """
    soul = server.soul
    return {
            A.server.ID: server.href,
            A.server.PUBLIC_IPS: soul.get('public_ip_addresses', []),
            A.server.PRIVATE_IPS: soul.get('private_ip_addresses', []),
            }


class Servers(Consul):
    """The consul for the RightScale servers."""
    def __init__(self, *args, **kwargs):
        super(Servers, self).__init__(*args, **kwargs)
        creds = self.provider.creds
        self.api = rightscale.RightScale(
                api_endpoint=creds[A.creds.API_ENDPOINT],
                refresh_token=creds[A.creds.REFRESH_TOKEN],
                )
        self.region_name = ''

    def find_servers(self, tags, running=True):
        # TODO: make stack and role be explicit args to find_servers instead of
        # {'stack': 'foo', 'role': 'bar'}
        deployment = tags[A.tags.STACK]
        name = tags[A.tags.ROLE]
        filters = ['name==%s' % name]
        if running:
            filters.append('state==operational')

        cloud = find_by_name(self.api.clouds, self.region_name)
        deployment = find_by_name(self.api.deployments, tags[A.STACK])
        filters.append('deployment_href==' + deployment.href)
        params = {'filter[]': filters}
        instances = cloud.instances.index(params=params)
        return [server_to_dict(i) for i in instances if i.soul['name'] == name]

    def set_region(self, region_name):
        self.region_name = region_name


class SecGroups(Consul):
    pass


class SecGroupRules(Consul):
    pass


class RightScale(Provider):
    CONSUL_MAP = {
            R.SERVERS: Servers,
            R.SERVER_SECURITY_GROUPS: SecGroups,
            R.SERVER_SECURITY_GROUP_RULES: SecGroupRules,
            }
