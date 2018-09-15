import uuid
from time import sleep

from charmhelpers.core import unitdata
from charmhelpers.core.hookenv import (
    log,
    config,
    status_set,
)

from charms.leadership import leader_get, leader_set

from charms.reactive import (
    clear_flag,
    endpoint_from_flag,
    hook,
    set_flag,
    when,
    when_any,
    when_not,
)

from charms.layer.aws_elb import (
    create_elb,
    create_listener,
    create_target_group,
    create_security_group_and_rule,
    describe_instance,
    get_cert_arn_for_fqdn,
    get_elb_status,
    get_elb_dns,
    register_target,
    # set_elb_subnets
)


kv = unitdata.kv()


@hook('start')
def set_started_flag():
    set_flag('aws-elb.juju.started')


@when('aws-elb.juju.started',
      'leadership.is_leader')
@when_not('leadership.set.elb_name')
def set_elb_name_to_leader():
    elb_uuid = str(uuid.uuid4())[:7]
    elb_name = 'juju-elb-{}'.format(elb_uuid)
    status_set('maintenance', "Configuring {}".format(elb_name))
    leader_set(elb_name=elb_name)


@when_not('leadership.set.subnets')
def block_on_no_subnets():
    conf = config()
    subnets = conf.get('subnets')
    if not subnets:
        status_set('blocked',
                   "Need 'subnets' cofigured to proceed")
        return
    else:
        status_set('maintenance', "Configuring subnets {}".format(subnets))
        leader_set(subnets=subnets)


@when('endpoint.aws.joined',
      'leadership.set.elb_name')
@when_not('aws-elb.cloud.request-sent')
def request_aws_enablement():
    """Request AWS enablement for provisioning ELB
    """
    status_set('maintenance', 'requesting cloud integration')
    cloud = endpoint_from_flag('endpoint.aws.joined')
    cloud.enable_acm_readonly()
    cloud.enable_instance_inspection()
    cloud.enable_load_balancer_management()
    cloud.enable_network_management()
    status_set('maintenance', 'Waiting for units to join')
    set_flag('aws-elb.cloud.request-sent')


@when('leadership.is_leader',
      'endpoint.aws-elb.available')
@when_not('leadership.set.listener_port')
def get_listener_port_from_endpoint():
    endpoint = endpoint_from_flag('endpoint.aws-elb.available')
    port = endpoint.list_unit_data()[0]['instance_port']
    leader_set(listener_port=port)


@when('leadership.is_leader',
      'endpoint.aws.ready',
      'endpoint.aws-elb.available')
@when_not('leadership.set.vpc_id',
          'leadership.set.aws_region')
def get_instance_data_for_elb_init():
    endpoint = endpoint_from_flag('endpoint.aws-elb.available')
    units_data = endpoint.list_unit_data()

    instance_region = units_data[0]['instance_region']
    instance_id = units_data[0]['instance_id']
    vpc_id = describe_instance(
        instance_id=instance_id,
        region_name=instance_region
    )['Reservations'][0]['Instances'][0]['VpcId']

    leader_set(aws_region=instance_region)
    leader_set(vpc_id=vpc_id)


@when('leadership.is_leader',
      'leadership.set.aws_region')
@when_not('leadership.set.cert_arn')
def initial_checks_for_fqdn_cert():
    """Set blocked status if we can't continue due to cert
    errors either on the charm config or existence of the cert
    in the ACM itself.
    """

    conf = config()
    elb_cert_fqdn = conf.get('cert-fqdn')
    if not elb_cert_fqdn:
        status_set('blocked',
                   "Need 'cert-fqdn' configured before we can continue")
        return
    else:
        cert_arn = get_cert_arn_for_fqdn(
            elb_cert_fqdn,
            leader_get('aws_region')
        )
        if not cert_arn:
            status_set('blocked', "'cert-fqdn' not found in ACM")
            return
        else:
            leader_set(cert_arn=cert_arn)


@when('leadership.set.elb_name',
      'leadership.set.aws_region',
      'leadership.set.cert_arn',
      'leadership.set.listener_port',
      'leadership.set.vpc_id',
      'leadership.set.subnets',
      'leadership.is_leader')
@when_not('leadership.set.tgt_grp_arn')
def init_elb():
    """Create the ELB, TGT, SG, and Listeners"""

    security_group_id = create_security_group_and_rule(
        name="{}-sg".format(leader_get('elb_name')),
        description="Juju created SG for {}".format(leader_get('elb_name')),
        region_name=leader_get('aws_region'),
        vpc_id=leader_get('vpc_id')
    )

    tgt_grp_arn = create_target_group(
        name="{}-tgt".format(leader_get('elb_name')),
        vpc_id=leader_get('vpc_id'),
        region_name=leader_get('aws_region'),
        port=int(leader_get('listener_port')),
        health_check_path='/ping'
    )['TargetGroups'][0]['TargetGroupArn']

    elb_arn = create_elb(
        name=leader_get('elb_name'),
        subnets=leader_get('subnets').split(","),
        security_groups=[security_group_id],
        region_name=leader_get('aws_region')
    )['LoadBalancers'][0]['LoadBalancerArn']

    create_listener(
        cert_arn=leader_get('cert_arn'),
        load_balancer_arn=elb_arn,
        target_group_arn=tgt_grp_arn,
        region_name=leader_get('aws_region')
    )

    status_set('waiting', "Waiting for ELB to become available...")
    while get_elb_status(elb_arn, leader_get('aws_region')) != 'active':
        sleep(1)
    status_set('active', "ELB, TGT, SG, and Listeners initialized")
    leader_set(elb_dns=get_elb_dns(elb_arn, leader_get('aws_region')))
    leader_set(tgt_grp_arn=tgt_grp_arn)
    leader_set(elb_arn=elb_arn)


@when('endpoint.aws-elb.available',
      'leadership.set.tgt_grp_arn')
@when_not('initial.targets.registered')
def register_initial_targets():
    endpoint = endpoint_from_flag('endpoint.aws-elb.available')
    units_data = endpoint.list_unit_data()
    status_set('maintenance', "Registering initial targets")
    for unit_data in units_data:
        register_target(
           target_group_arn=leader_get('tgt_grp_arn'),
           instance_id=unit_data['instance_id'],
           region_name=leader_get('aws_region')
        )
    status_set('active', "{} available".format(leader_get('elb_name')))
    set_flag('initial.targets.registered')


@when('endpoint.aws-elb.changed',
      'leadership.set.tgt_grp_arn')
def register_subsequent_targets():
    endpoint = endpoint_from_flag('endpoint.aws-elb.changed')
    units_data = endpoint.list_unit_data()

    for unit_data in units_data:
        register_target(
           target_group_arn=leader_get('tgt_grp_arn'),
           instance_id=unit_data['instance_id'],
           region_name=leader_get('aws_region')
        )
        status_set('active',
                   "Registered {} with tgt_grp".format(
                       unit_data['instance_id']))

    status_set('active', "{} available".format(leader_get('elb_name')))
    clear_flag('endpoint.aws-elb.changed')


@when_not('endpoint.aws-elb.joined')
def block_on_no_elb_rel():
    status_set('blocked', "Need relation to aws-elb provider to continue")
    return
