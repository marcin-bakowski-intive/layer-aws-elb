import uuid
from time import sleep

from charmhelpers.core import unitdata
from charmhelpers.core.hookenv import (
    atexit,
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
    delete_listener,
    delete_load_balancer,
    delete_security_group,
    delete_target_group,
    deregister_targets,
    describe_instance,
    get_cert_arn_for_fqdn,
    get_elb_dns,
    get_elb_listener_arns,
    get_elb_status,
    get_health_by_target,
    get_targets,
    get_targets_health,
    register_target,
)


kv = unitdata.kv()


@hook('start')
def set_started_flag():
    set_flag('aws-elb.juju.started')


@hook('update-status')
def update_status():
    """Set the update-status flag during the update-status hook."""
    set_flag('update-status')
    atexit(clear_flag, 'update-status')


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
      'aws-elb.juju.started')
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
      'endpoint.aws.ready',
      'endpoint.aws-elb.available')
@when_not('leadership.set.listener_tls_port',
          'leadership.set.listener_raw_port',
          'leadership.set.instance_port',
          'leadership.set.instance_protocol',
          'leadership.set.health_check_endpoint',
          'leadership.set.aws_region',
          'leadership.set.vpc_id')
def get_initial_data_from_endpoint():
    """Set the name of the ELB and get initial instance data
    """
    endpoint = endpoint_from_flag('endpoint.aws-elb.available')
    units_data = endpoint.list_unit_data()

    if not len(units_data) > 0:
        status_set('blocked',
                   "Something is wrong, no instances found on relation")
        return

    conf = config()

    instance_id = units_data[0]['instance_id']
    instance_port = units_data[0]['instance_port']
    instance_protocol = conf['instance-protocol']
    health_check_endpoint = units_data[0]['health_check_endpoint']
    instance_region = units_data[0]['instance_region']

    vpc_id = describe_instance(
        instance_id=instance_id,
        region_name=instance_region
    )['Reservations'][0]['Instances'][0]['VpcId']

    leader_set(aws_region=instance_region)
    leader_set(vpc_id=vpc_id)
    leader_set(listener_tls_port=conf['listener-tls-port'])
    leader_set(listener_raw_port=conf['listener-raw-port'])
    leader_set(instance_port=instance_port)
    leader_set(instance_protocol=instance_protocol)
    leader_set(health_check_endpoint=health_check_endpoint)

    for port_type in ('tls', 'raw'):
        port = conf.get('listener-{}-port'.format(port_type))
        if port:
            leader_set(**{'listener_{}_port'.format(port_type): port})


@when('leadership.is_leader',
      'leadership.set.aws_region')
@when_not('leadership.set.cert_arn')
def initial_checks_for_fqdn_cert():
    """Set blocked status if we can't continue due to cert
    errors either on the charm config or existence of the cert
    in the ACM itself.
    """

    conf = config()
    listener_raw_port = conf.get('listener-raw-port')
    listener_tls_port = conf.get('listener-tls-port')
    elb_cert_fqdn = conf.get('cert-fqdn')
    if listener_raw_port and not listener_tls_port:
        # only non-TLS connectivity configured
        leader_set(cert_arn='')
    elif not elb_cert_fqdn:
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


@when('leadership.set.aws_region',
      'leadership.set.cert_arn',
      'leadership.set.health_check_endpoint',
      'leadership.set.vpc_id',
      'leadership.set.subnets',
      'leadership.is_leader')
@when_any('leadership.set.listener_tls_port',
          'leadership.set.listener_raw_port')
@when_not('leadership.set.tgt_grp_arn',
          'leadership.set.elb_name',
          'leadership.set.elb_arn',
          'leadership.set.security_group_id',
          'leadership.set.tgt_grp_arn')
def init_elb():
    """Create the ELB, TGT, SG, and Listeners"""

    # Create uuid to use for the ELB name postfix
    elb_uuid = str(uuid.uuid4())[:7]
    elb_name = 'juju-elb-{}'.format(elb_uuid)
    status_set('maintenance', "Provisioning {}".format(elb_name))

    ports = {
        port_type: int(port)
        for port_type in ('tls', 'raw')
        for port in [leader_get('listener_{}_port'.format(port_type))]
        if port and port.isdigit() and int(port)
    }

    instance_protocol = leader_get('instance_protocol').upper()
    elb_type = 'application' if instance_protocol.startswith('HTTP') else 'network'

    if elb_type == 'application':
        security_group_id = create_security_group_and_rule(
            name="{}-sg".format(elb_name),
            description="Juju created SG for {}".format(elb_name),
            region_name=leader_get('aws_region'),
            vpc_id=leader_get('vpc_id'),
            **ports,
        )
        security_groups = [security_group_id]
    else:
        security_group_id = ''
        security_groups = []

    tgt_grp_arn = create_target_group(
        name="{}-tgt".format(elb_name),
        vpc_id=leader_get('vpc_id'),
        region_name=leader_get('aws_region'),
        protocol=instance_protocol,
        port=int(leader_get('instance_port')),
        health_check_path=leader_get('health_check_endpoint')
    )['TargetGroups'][0]['TargetGroupArn']

    elb_arn = create_elb(
        name=elb_name,
        subnets=leader_get('subnets').split(","),
        security_groups=security_groups,
        scheme=config('scheme'),
        region_name=leader_get('aws_region'),
        elb_type=elb_type,
    )['LoadBalancers'][0]['LoadBalancerArn']

    encrypted_counterpart = {
        'HTTP': 'HTTPS',
        'TCP': 'TLS',
    }
    for port_type, port in ports.items():
        if port_type == 'tls':
            protocol = encrypted_counterpart[instance_protocol.upper()]
        else:
            protocol = instance_protocol.upper()
            assert protocol in {'HTTP', 'TCP', 'UDP', 'TCP_UDP'}
        create_listener(
            cert_arn=leader_get('cert_arn'),
            load_balancer_arn=elb_arn,
            target_group_arn=tgt_grp_arn,
            region_name=leader_get('aws_region'),
            protocol=protocol,
            port=port,
        )

    status_set('waiting',
               "Waiting for {} to become available...".format(elb_name))

    while get_elb_status(elb_arn, leader_get('aws_region')) != 'active':
        sleep(1)

    status_set('active', "ELB, TGT, SG, and Listeners initialized")

    leader_set(elb_arn=elb_arn)
    leader_set(elb_dns=get_elb_dns(elb_arn, leader_get('aws_region')))
    leader_set(elb_name=elb_name)

    leader_set(security_group_id=security_group_id)
    leader_set(tgt_grp_arn=tgt_grp_arn)


@when('endpoint.aws-elb.available',
      'leadership.set.elb_name',
      'leadership.set.tgt_grp_arn',
      'leadership.set.aws_region')
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
    update_target_health(endpoint)


@when('endpoint.aws-elb.changed',
      'leadership.set.tgt_grp_arn')
def register_subsequent_targets():
    endpoint = endpoint_from_flag('endpoint.aws-elb.changed')
    units_data = endpoint.list_unit_data()

    unmatched_targets = set(get_targets(
        target_group_arn=leader_get('tgt_grp_arn'),
        region_name=leader_get('aws_region')
    ))

    for unit_data in units_data:
        register_target(
           target_group_arn=leader_get('tgt_grp_arn'),
           instance_id=unit_data['instance_id'],
           region_name=leader_get('aws_region')
        )
        unmatched_targets.discard(unit_data['instance_id'])
        status_set('active',
                   "Registered {} with tgt_grp".format(
                       unit_data['instance_id']))

    if unmatched_targets:
        deregister_targets(
            targets=unmatched_targets,
            target_group_arn=leader_get('tgt_grp_arn'),
            region_name=leader_get('aws_region')
        )

    status_set('active', "{} available".format(leader_get('elb_name')))
    clear_flag('endpoint.aws-elb.changed')
    update_target_health(endpoint)


def update_target_health(endpoint):
    endpoint.publish_dns_and_health(
        elb_dns=leader_get('elb_dns'),
        health_by_target=get_health_by_target(
            target_group_arn=leader_get('tgt_grp_arn'),
            region_name=leader_get('aws_region'),
        ),
    )


@when('initial.targets.registered',
      'update-status')
def targets_health_check_status():
    target_statuses = get_targets_health(
        target_group_arn=leader_get('tgt_grp_arn'),
        region_name=leader_get('aws_region')
    )
    status_set('active',
               "{} - {}".format(
                   leader_get('elb_name'),
                   str(list(set(target_statuses)))))
    endpoint = endpoint_from_flag('endpoint.aws-elb.available')
    update_target_health(endpoint)


@when('endpoint.aws.ready')
@when_not('endpoint.aws-elb.joined')
def block_on_no_elb_rel():
    status_set('blocked', "Need relation to aws-elb provider to continue")
    return


@when_not('endpoint.aws-elb.available')
@when('leadership.set.elb_name',
      # 'leadership.set.elb_arn'
      # 'leadership.set.elb_dns'
      # 'leadership.set.aws_region',
      # 'leadership.set.cert_arn',
      # 'leadership.set.listener_tls_port',
      # 'leadership.set.listener_raw_port',
      # 'leadership.set.health_check_endpoint',
      # 'leadership.set.vpc_id',
      # 'leadership.set.subnets',
      'leadership.is_leader')
def remove_all_provisioned_aws_resources():
    status_set('maintenance', "Removing provisioned AWS resources")

    target_group_arn = leader_get('tgt_grp_arn')
    elb_arn = leader_get('elb_arn')
    aws_region = leader_get('aws_region')
    security_group_id = leader_get('security_group_id')

    targets = get_targets(target_group_arn, aws_region)

    for listener_arn in get_elb_listener_arns(elb_arn, aws_region):
        delete_listener(listener_arn, aws_region)

    delete_load_balancer(
        elb_arn,
        aws_region
    )

    deregister_targets(
        targets,
        target_group_arn,
        aws_region
    )

    delete_target_group(
        target_group_arn,
        aws_region
    )

    if security_group_id:
        delete_security_group(security_group_id, aws_region)

    # Unset leader values
    leader_set(elb_name=None)
    leader_set(elb_arn=None)
    leader_set(elb_dns=None)
    leader_set(aws_region=None)
    leader_set(cert_arn=None)
    leader_set(listener_tls_port=None)
    leader_set(listener_raw_port=None)
    leader_set(health_check_endpoint=None)
    leader_set(vpc_id=None)
    leader_set(subnets=None)
    leader_set(security_group_id=None)
    leader_set(tgt_grp_arn=None)

    # Unset flags
    clear_flag('initial.targets.registered')
    clear_flag('endpoint.aws-elb.available')
    status_set('active', "AWS resources fully removed")
