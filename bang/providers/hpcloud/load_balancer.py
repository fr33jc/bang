import requests
import json
from ...util import log

class HPLoadBalancer():
    """
    Convenience functions to manage HP cloud LBaaS instances. 
    LBaaS uses its own AZ-independent public URL for management,
    but accepts the common auth token. Rather than integrating with
    openstack, this is HP-cloud specific for now, since there is still
    disagreement about the direction openstack's load balancing effort
    will take.

    TODO: The beta api doesn't seem to support tags, which we use elsewhere
    for filtering a stack. Instead this'll use 'name'
    """
    def __init__(self, hpcloud):
        """
        Provide a management URL (from the openstack service catalog)
        and auth token (which can be pinched from novaclient)
        """
        self.auth_token = hpcloud.os_auth_token
        self.catalog = filter(lambda c: c['name'] == 'Load Balancer', 
                              hpcloud.os_catalog['access']['serviceCatalog'])

        self.management_url = None

    def set_region(self, region_name):
        region_lb = filter(lambda c: c['region'] == region_name,
                                   self.catalog[0]['endpoints'])
        if not region_lb:
            available_regions = [c['region'] 
                                 for c in self.catalog[0]['endpoints']]
            raise Exception("No LB provider matching region %s (%s)" %
                    (region_name, available_regions))
        self.management_url = region_lb[0]['publicURL']


    def list_lbs(self):
        """
        Lists all LBaaS instances. To get details (nodes, external IPs)
        use the ``lb_details`` call.

        :rtype :class:`list` of :class:`dict`
        """
        resp, body = self._request('get', '/loadbalancers')
        return body['loadBalancers']

    def lb_details(self, lb_id):
        """
        Get details (including all nodes and external IPs)

        :param string lb_id:  Load balancer id

        :rtype :class:`dict`
        """
        resp, body = self._request('get', '/loadbalancers/%s' % lb_id)
        return body

    def find_lb_by_name(self, name):
        """
        Look up a LBaaS instance by name (rather than id)

        :attr string name:  The LBaaS name assigned at creation time

        :rtype :class:`dict`
        """
        log.debug("Finding load balancers matching name '%s'" % name)
        matching = filter(lambda l: l['name'] == name, self.list_lbs())
        if len(matching) > 1:
            raise ValueError("Ambiguous; more than one load balancer matched '%s'" % name)
        if matching:
            log.info("Found existing load balancer, %s" % matching[0]['id'])
            return matching[0]
        return None

    def create_lb(self, name, protocol='HTTP', port=80, algorithm=None,
            virtual_ips=[], nodes=[], node_port=None):
        """
        Create a new LBaaS instance. A name is required. If no nodes
        are required, the instance ``status`` (after it's built) will be
        ``ERROR`` until nodes are added. The return dict contains the id
        and ``virtualIps`` (the external IP).

        :param string name:  The LBaaS name - should be unique

        :param string protocol:  Supported: HTTP, TCP

        :param int port:  The external port. Supported: 80, 443, seemingly

        :param list virtual_ips:  Use an existing IP (allows multiple
                                  ports per IP)

        :param list nodes:  Nodes addresses to add
        """
        log.info("Creating load balancer '%s'" % name)
        protocol = protocol.upper()
        nodes_to_add = []
        if nodes:
            nodes_to_add = map(
                    lambda n: {'address': n, 'port': str(node_port)}, 
                    nodes
                    )
        data = {
            'name': name,
            'protocol': protocol,
            'port': str(port),
            'nodes': nodes_to_add,
        }
        if virtual_ips:
            data['virtualIps'] = map(lambda i: {'id': i}, virtual_ips)
        if algorithm:
            data['algorithm'] = algorithm
        resp, body = self._request('post', '/loadbalancers', data=data)
        return body

    def delete_lb(self, lb_id):
        """
        Delete an instance

        :param string lb_id:  Delete this LBaaS id
        """
        log.info("Deleting load balancer %s" % lb_id)
        self._request('delete', '/loadbalancers/%s' % lb_id)

    def add_lb_nodes(self, lb_id, nodes):
        """
        Adds nodes to an existing LBaaS instance

        :param string lb_id:  Balancer id

        :param list nodes:  Nodes to add. {address, port, [condition]}

        :rtype :class:`list`
        """
        log.info("Adding load balancer nodes %s" % nodes)
        resp, body = self._request(
                'post', 
                '/loadbalancers/%s/nodes' % lb_id,
                data={'nodes': nodes})
        return body

    def match_lb_nodes(self, lb_id, existing_nodes, host_addresses, host_port):
        """
        Add and remove nodes to match the host addresses
        and port given, based on existing_nodes. HPCS doesn't
        allow a load balancer with no backends, so we'll add
        first, delete after.

        :param string lb_id: Load balancer id

        :param :class:`list` of :class:`dict` existing_nodes: Existing nodes

        :param :class:`list` host_addresses: Node host addresses

        :param string port: Node port
        """
        delete_filter = lambda n: \
                n['address'] not in host_addresses or \
                str(n['port']) != str(host_port)

        delete_nodes = filter(delete_filter, existing_nodes)
        delete_node_ids = [n['id'] for n in delete_nodes]
        delete_node_hosts = [n['address'] for n in delete_nodes]
        
        current_nodes = set([n['address'] for n in existing_nodes])
        current_nodes -= set(delete_node_hosts)
        add_nodes = host_addresses - current_nodes
        
        if add_nodes:
            nodes_to_add = [
                    {'address': n, 'port': str(host_port)}
                    for n in add_nodes
            ]
            args = (lb_id, nodes_to_add)
            self.add_lb_nodes(*args)

        if delete_node_ids:
            args = (lb_id, delete_node_ids)
            self.remove_lb_nodes(*args)
        
        log.info("Were %d nodes. Added %d nodes; deleted %d nodes" % 
                (len(existing_nodes), len(add_nodes), len(delete_nodes)))

    def remove_lb_nodes(self, lb_id, node_ids):
        """
        Remove one or more nodes

        :param string lb_id:  Balancer id

        :param list node_ids:  List of node ids
        """
        log.info("Removing load balancer nodes %s" % node_ids)
        for node_id in node_ids:
            self._request('delete', '/loadbalancers/%s/nodes/%s' % (lb_id, node_id))

    def update_lb_node_condition(self, lb_id, node_id, condition):
        """
        Update node condition - specifically to disable/enable

        :param string lb_id:  Balancer id

        :param string node_id:  Node id

        :param string condition:  ENABLED/DISABLED
        """
        self._request(
                'put', 
                '/loadbalancers/%s/nodes/%s' % (lb_id, node_id),
                data={'condition': condition})
        
    def _request(self, method, url, data=None, **kwargs):
        if not self.management_url:
            raise Exception("Call set_region first")
        kwargs.setdefault('headers', {})['X-Auth-Token'] = self.auth_token
        kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
        if data:
            if isinstance(data, dict):
                kwargs['data'] = json.dumps(data)
            else:
                kwargs['data'] = data

        url = '%s%s' % (self.management_url, url)
        resp = requests.request(method, url, **kwargs)
        if resp.text:
            try:
                body = json.loads(resp.text)
            except ValueError:
                body = None
        else:
            body = None
        resp.raise_for_status()
        return resp, body

