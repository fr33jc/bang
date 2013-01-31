Bang!
=====


*The beginning of the universe...*


Overview
--------
Bang automates deployment of server-based software projects.

Projects often comprise multiple servers of varying roles, public cloud
resources like storage *buckets* and message queues and other
IaaS/PaaS/Splat_aaS resources.  DevOps teams already use several configuration
management tools like Ansible, Salt Stack, Puppet and Chef to automate
on-server configuration.  There are also cloud resource *orchestration* tools
like CloudFormation and Orchestra/Juju that can be used to automate cloud
resource provisioning.  Bang combines orchestration with on-server
configuration management to provide one-shot, automated deployment of entire
project *stacks*.

Bang instantiates cloud resources (e.g. AWS EC2/OpenStack Nova server
instances), then leverages `Ansible <http://ansible.cc/>`_ for server
configuration.

The latest online documentation lives at http://fr33jc.github.com/bang/.
