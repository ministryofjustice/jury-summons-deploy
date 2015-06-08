CoreOS on AWS - deploy repo
===========================

This repo helps you create and manage a CoreOS architecture on AWS.

It was originally created for the Jury Summons project at MoJ but it can easily be used for any other projects.

Technologies used:

* [CoreOS](https://coreos.com) including fleet, etcd, flannel
* [Confd](https://github.com/kelseyhightower/confd)
* [Docker](http://www.docker.com)
* [Fabric](http://www.fabfile.org)
* [AWS Cloud Formation](http://aws.amazon.com/cloudformation/)


Architecture
============

* VPC containing
  * Public Subnets (one per AZ) containing
    * ELB
    * NAT
    * SSH Bastion
  * Private Subnects (one per AZ) containing
    * Etcd Cluster (1+ instances)
    * CoreOS Cluster (1+ instances)
    * RDS


Getting started
===============

* create and activate a virtualenv

    virtualenv --no-site-packages venv && source venv/bin/activate

* install dependencies

    pip install -r requirements.txt

* populate your ~/.aws/credentials
* install fleetctl locally (e.g. `brew install fleetctl`)

Now you can use fabric to create/update your stack, manage your clusters and deploy your code.

