Bang!
=====


*The beginning of the universe...*


Overview
--------
Bang automates deployment of server-based software projects.

Projects often comprise multiple servers of varying roles and in varying
locations (e.g. traditional server room, cloud provider, multi-datacenter),
public cloud resources like storage *buckets* and message queues and other
IaaS/PaaS/Splat_aaS resources.  DevOps teams already use several configuration
management tools like Ansible, Salt Stack, Puppet and Chef to automate
on-server configuration.  There are also cloud resource *orchestration* tools
like CloudFormation and Orchestra/Juju that can be used to automate cloud
resource provisioning.  Bang combines orchestration with on-server
configuration management to provide one-shot, automated deployment of entire
project *stacks*.

Bang instantiates cloud resources (e.g. AWS EC2/OpenStack Nova server
instances), then leverages `Ansible <http://www.ansible.com/>`_ for
configuration of all servers whether they are in a server room in the office,
across the country in a private datacenter, or hosted by a public cloud
provider.

The latest online documentation lives at http://bang.readthedocs.org/.

.. image:: https://travis-ci.org/fr33jc/bang.png
    :target: http://travis-ci.org/fr33jc/bang
