from collections import defaultdict
import os
import time
import json
import lazy_object_proxy
import random
from functools import partial

import boto.cloudformation
import boto.ec2
from boto.exception import BotoServerError

from fabric.api import task, env, local, run
from fabric.tasks import execute
from fabric import colors

import yaml
import requests

from aws.templates.app_cluster import get_template


SMOKE_TEST_SLEEP = 10  # in secs
SMOKE_TEST_WAIT_TIME = 60*10  # in secs


def get_vpc_id():
    """
    Returns the VPC ID of the running `stack_name`
    """
    resources = env.cf.describe_stack_resources(env.stack_name, 'VPC')
    if not resources:
        return Exception('%s not running or not ready' % env.stack_name)
    return resources[0].physical_resource_id


def get_hosts_for_role(role, limit_to_one=False):
    instances = [i.private_ip_address for i in env.ec2.get_only_instances(
        filters={
            'tag:Role': role,
            'instance-state-name': 'running',
            'vpc-id': get_vpc_id()
        }
    )]

    if limit_to_one:
        instances = [random.choice(instances)]
    return instances


def template_body():
    return get_template(
        region=env.env_conf['region'],
        coreos_ami=str(env.coreos_ami),
        dns_suffix=env.stack_base_name + '.dsd.io.'
    ).to_json()


def _get_gateway():
    instances = env.ec2.get_only_instances(filters={
        'tag:Role': 'SSHBastion',
        'instance-state-name': 'running',
        'vpc-id': get_vpc_id()
    })
    return instances[0].public_dns_name


def _get_stack_name():
    return "%s-%s" % (env.stack_base_name, env.env_name)


def _get_env_conf():
    """
        Returns a dict of all key/value pairs defined in the
        environments.yml

        env-specific settings override the base ones
    """
    # load and get base
    conf = yaml.load(open('environments.yml', 'r'))
    env_conf = conf['base'].copy()

    # override with specific env config if exists
    env_conf.update(conf['environments'].get(env.env_name, {}))

    env_conf['EnvName'] = env.env_name

    return env_conf


def _get_stack_params():
    """
        Same as _get_env_conf but filtering out all the Parameters
        which are NOT part of the cloud formation template
    """
    cf_template = json.loads(template_body())
    cf_params = cf_template['Parameters'].keys()
    return {k: v for k, v in env.env_conf.items() if k in cf_params}


def _get_latest_coreos_ami():
    import datetime

    images = env.ec2.get_all_images(
        filters={
            'virtualization-type': 'hvm',
            'architecture': 'x86_64',
            'owner-id': '595879546273',
            'state': 'available',
            'root-device-type': 'ebs',
            'name': 'CoreOS-beta-*-hvm'
        }
    )

    current_image = None
    current_creation_date = datetime.datetime(1990, 1, 1)
    for image in images:
        creation_date = datetime.datetime.strptime(
            image.creationDate, "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        if creation_date > current_creation_date:
            current_creation_date = creation_date
            current_image = image

    return current_image.id


os.environ['AWS_PROFILE'] = 'jury'

env.stack_base_name = 'jurysummons'
env.env_name = 'test'
env.env_conf = lazy_object_proxy.Proxy(_get_env_conf)
env.stack_params = lazy_object_proxy.Proxy(_get_stack_params)
env.gateway = lazy_object_proxy.Proxy(_get_gateway)
env.stack_name = lazy_object_proxy.Proxy(_get_stack_name)
env.coreos_ami = lazy_object_proxy.Proxy(_get_latest_coreos_ami)

env.cf = lazy_object_proxy.Proxy(
    lambda: boto.cloudformation.connect_to_region(env.env_conf['region'])
)
env.ec2 = lazy_object_proxy.Proxy(
    lambda: boto.ec2.connect_to_region(env.env_conf['region'])
)


@task
def workon(role):
    env.hosts = get_hosts_for_role(role, limit_to_one=True)


@task
def ssh():
    local('ssh -A -o "ProxyCommand ssh -A -W %h:%p {user}@{gw}" {user}@{target}'.format(
        user=env.user, gw=env.gateway, target=env.hosts[0]
    ))


@task
def environ(env_name):
    env.env_name = env_name


@task
def user(user):
    env.user = user


@task
def monitor_stack_events():
    status_fmt = "{0: <8} | {1: <32} | {2: <34} | {3: <18}"

    print status_fmt.format('Time', 'Resource Type', 'Resource ID', 'Status')
    print '=' * 101

    last_evt_id = None

    while True:
        evt = env.cf.describe_stack_events(env.stack_name)[0]

        if evt.event_id != last_evt_id:
            last_evt_id = evt.event_id

            if evt.resource_status.endswith('_IN_PROGRESS'):
                status = colors.yellow(evt.resource_status)
            elif evt.resource_status.endswith('_COMPLETE'):
                status = colors.green(evt.resource_status)
            else:
                status = evt.resource_status

            timestr = evt.timestamp.strftime("%H:%M:%S")
            resource_type = evt.resource_type.replace('AWS::', '')

            print ("%s\r" % status_fmt).format(
                timestr, resource_type[:32], evt.logical_resource_id[:34],
                status)

            if (evt.resource_status.endswith('_COMPLETE') and
                    evt.resource_type == 'AWS::CloudFormation::Stack'):
                print ""
                break

        time.sleep(1)


def cf_output(key):
    cf_outputs = env.cf.describe_stacks(env.stack_name)[0].outputs
    return filter(lambda x: x.key == key, cf_outputs)[0].value


@task
def populate_etcd():
    etcd_cluster_host = get_hosts_for_role('EtcdCluster', limit_to_one=True)

    # DB settings
    db_params = {
        'hostname': cf_output('PrimaryDBHostname'),
        'ipv4_addr': cf_output('PrimaryDBHostname'),
        'port': cf_output('PrimaryDBPort'),
        'username': env.env_conf['DBUsername'],
        'password': env.env_conf['DBPassword'],
        'database': env.env_conf['DBName']
    }

    execute(
        run,
        "etcdctl set /services/postgres '%s'" % json.dumps(db_params),
        hosts=etcd_cluster_host
    )

    # SQS settings
    sqs_params = {
        'access_key': cf_output('SQSAccessKey'),
        'secret_key': cf_output('SQSSecretKey')
    }

    execute(
        run,
        "etcdctl set /services/sqs '%s'" % json.dumps(sqs_params),
        hosts=etcd_cluster_host
    )

    # elb settings
    elb_params = {
        'name': cf_output('PublicELBName'),
        'iam_access_key': cf_output('PublicELBAccessKey'),
        'iam_secret_access_key': cf_output('PublicELBSecretAccessKey'),
    }

    for k, v in elb_params.items():
        execute(
            run,
            "etcdctl set /services/public-elb/%s '%s'" % (k, v),
            hosts=etcd_cluster_host
        )

    # aws region
    execute(
        run,
        "etcdctl set /aws/region '%s'" % cf_output('Region'),
        hosts=etcd_cluster_host
    )

    execute(run, "etcdctl set /aws/env '%s'" % env.stack_name,
            hosts=etcd_cluster_host)

    # dns
    dns_settings = {
        'current': cf_output('PublicELBDNSRecord'),
        'previous': cf_output('PublicPreviousELBDNSRecord'),
        'next': cf_output('PublicNextELBDNSRecord'),
    }

    for k, v in dns_settings.items():
        execute(
            run,
            "etcdctl set /aws/dns/%s '%s'" % (k, v),
            hosts=etcd_cluster_host
        )


@task
def get_etcd(key):
    execute(
        run,
        "etcdctl get %s" % key,
        hosts=get_hosts_for_role('EtcdCluster', limit_to_one=True)
    )


@task
def fleetctl(cmd, capture=False):
    return local(('fleetctl --tunnel {gw}:22 --ssh-username={user} --driver=etcd '
           '--strict-host-key-checking=false '
           '--endpoint=http://{endpoint}:2379 {cmd}').format(
           gw=env.gateway, user=env.user, cmd=cmd,
           endpoint=get_hosts_for_role('EtcdCluster', limit_to_one=True)[0]
    ), shell='/bin/bash', capture=capture)


@task
def does_stack_exist():
    try:
        env.cf.describe_stacks(str(env.stack_name))
    except BotoServerError as e:
        if e.message == 'Stack with id %s does not exist' % env.stack_name:
            return False
        else:
            raise
    return True


@task
def create_stack():
    stack_params = dict(env.stack_params)

    # create new DiscoveryURL
    cluster_size = stack_params.get('EtcdClusterSize', 3)
    stack_params['DiscoveryURL'] = requests.get(
        'https://discovery.etcd.io/new?size=%s' % cluster_size
    ).content

    # create stack
    env.cf.create_stack(
        env.stack_name,
        template_body=template_body(),
        parameters=stack_params.items(),
        capabilities=['CAPABILITY_IAM']
    )

    monitor_stack_events()


@task
def update_stack():
    stack = env.cf.describe_stacks(env.stack_name)[0]

    # use same params that the stack was created with, unless values in
    # environment.yml have changed
    stack_params = {p.key: p.value for p in stack.parameters}
    stack_params.update(env.stack_params)

    env.cf.update_stack(
        env.stack_name,
        template_body=template_body(),
        parameters=stack_params.items(),
        capabilities=['CAPABILITY_IAM']
    )


@task
def create_or_update_stack():
    if does_stack_exist():
        try:
            update_stack()
        except BotoServerError as e:
            if e.message == 'No updates are to be performed.':
                pass
            else:
                raise
    else:
        create_stack()


SERVICES_SOURCE_DIR = os.path.join(
    os.path.dirname(__file__), 'unitfiles', 'aws', 'templates'
)
SERVICES_DEST_DIR = os.path.join(
    os.path.dirname(__file__), 'unitfiles', 'aws', '_build'
)


def get_version(deploy_tag, web_tag):
    return '.%s-%s' % (deploy_tag, web_tag)


@task
def make_services(deploy_tag, web_tag):
    import shutil
    from jinja2 import FileSystemLoader, Environment

    # delete and re-create dest folder
    shutil.rmtree(SERVICES_DEST_DIR, ignore_errors=True)
    os.makedirs(SERVICES_DEST_DIR)

    tmpl_env = Environment(
        loader=FileSystemLoader(searchpath=SERVICES_SOURCE_DIR)
    )

    services = []
    version = get_version(deploy_tag, web_tag)
    for tmpl_name in tmpl_env.list_templates():
        tmpl_filename, tmpl_ext = os.path.splitext(tmpl_name)
        if tmpl_ext != '.jinja':
            shutil.copy(os.path.join(SERVICES_SOURCE_DIR, tmpl_name), SERVICES_DEST_DIR)
            services.append(tmpl_filename)
            continue

        # generate service name:
        #   <file-name>.<deploy-tag>-<web-tag>[@]
        filename_parts = tmpl_filename.split('@')
        filename_parts[0] = '%s%s' % (filename_parts[0], version)
        output_filename = '@'.join(filename_parts)

        output_path = os.path.join(SERVICES_DEST_DIR, '%s.service' % output_filename)

        tmpl = tmpl_env.get_template(tmpl_name)

        # write the processed file to dest folder
        with open(output_path, "wb") as f:
            f.write(tmpl.render({
                'version': version,
                'deploy_tag': deploy_tag,
                'web_tag': web_tag
            }))
        services.append(output_filename)

    return services


def update_x_version(x, deploy_tag, web_tag, action):
    version = get_version(deploy_tag, web_tag)

    etcd_cluster_host = get_hosts_for_role('EtcdCluster', limit_to_one=True)
    execute(
        run,
        "etcdctl %s /services/meta/%s '%s'" % (action, x, version),
        hosts=etcd_cluster_host
    )


update_previous_version = partial(update_x_version, 'previous')
update_current_version = partial(update_x_version, 'current')
update_next_version = partial(update_x_version, 'next')


@task
def pre_deploy(deploy_tag, web_tag):
    populate_etcd()
    service_instances = make_services_and_get_names(deploy_tag, web_tag)

    execute(fleetctl, "submit %s/*" % SERVICES_DEST_DIR)
    # execute(fleetctl, "load %s" % ' '.join(service_instances))
    execute(fleetctl, "start %s" % ' '.join(service_instances))

    update_next_version(deploy_tag, web_tag, 'set')


def make_services_and_get_names(deploy_tag, web_tag):
    service_names = make_services(deploy_tag, web_tag)
    # TODO this should be somewhere in the config file
    service_instances = []
    for service in service_names:
        if '@' in service:
            service_instances.append('%s1' % service)
            service_instances.append('%s2' % service)
        else:
            service_instances.append(service)
    return service_instances


@task
def post_deploy(deploy_tag, web_tag):
    update_current_version(deploy_tag, web_tag, 'set')
    update_next_version(deploy_tag, web_tag, 'rm')

    env.host_string = get_hosts_for_role('EtcdCluster', limit_to_one=True)[0]
    service_keys = run('etcdctl ls /_coreos.com/fleet/states/').split()
    status = defaultdict(dict)
    for units_service in service_keys:
        service_name = os.path.split(units_service)[-1]
        unit_keys = run('etcdctl ls {}'.format(units_service)).split()
        for unit in unit_keys:
            unit_name = os.path.split(unit)[-1]
            status[service_name][unit_name] = json.loads(run('etcdctl get {}'.format(unit)))


    units_that_should_be_active = make_services_and_get_names(deploy_tag, web_tag)
    units_that_should_be_active = [x+'.service' for x in units_that_should_be_active]

    for unit, info in status.items():
        if unit not in units_that_should_be_active:
            execute(
                fleetctl, "unload %s" % unit
            )
            execute(
                fleetctl, "destroy %s" % unit
            )


@task
def smoke_test(deploy_tag, web_tag):
    version = get_version(deploy_tag, web_tag)
    env.host_string = get_hosts_for_role('EtcdCluster', limit_to_one=True)[0]
    next_url = run('etcdctl get /aws/dns/next/').strip()
    full_url = 'http://%s' % next_url

    is_OK = False
    attempts = 0
    while not is_OK and attempts < (SMOKE_TEST_WAIT_TIME / SMOKE_TEST_SLEEP):
        response = requests.get(full_url)
        if response.ok:
            header_version = response.headers.get('x-app-version', '__invalid__')
            is_OK = header_version == version
        time.sleep(10)
        attempts += 1

    if not is_OK:
        raise Exception(
            'Next not responding, cannot complete deploy (%s)' % full_url
        )


@task
def deploy(deploy_tag, web_tag):
    create_or_update_stack()
    pre_deploy(deploy_tag, web_tag)
    smoke_test(deploy_tag, web_tag)
    post_deploy(deploy_tag, web_tag)


# unload and destroy ALL unit files
# fleetctl list-unit-files | tail -n +2 | cut -d '.' -f 1 | xargs fleetctl unload
# fleetctl list-unit-files | tail -n +2 | cut -d '.' -f 1 | xargs fleetctl destroy


# free space
# docker rm `docker ps -a | grep Exited | awk '{print $1 }'`
# docker rmi `docker images -aq`
