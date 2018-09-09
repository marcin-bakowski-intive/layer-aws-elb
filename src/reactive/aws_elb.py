import os

from charmhelpers.core import unitdata
from charmhelpers.core.hookenv import (
    config,
    status_set,
)

from charms.leadership import leader_get, leader_set

from charms.reactive import (
    endpoint_from_flag,
    when,
    hook,
    when_not,
    when_any,
    when_none,
    set_flag,
    clear_flag
)

from charms.layer.elb_aws import (
    create_elb,
    create_listener,
    create_target_group,
    create_security_group_and_rule,
    describe_instance,
    get_cert_arn_for_fqdn,
    register_target,
)


kv = unitdata.kv()


@hook('start')
def set_started_flag():
    set_flag('aws-elb.juju.started')


@when('aws-elb.juju.started',
      'leadership.is_leader')
@when_not('leadership.set.elb_name')
def set_elb_name_to_leader(): 
    elb_uuid = os.getenv('JUJU_MODEL_UUID')[:7]
    elb_name = 'juju-elb-{}'.format(elb_uuid)
    leader_set(elb_name=elb_name)


@when('endpoint.aws.joined',
      'aws-elb.juju.started',
      'leadership.set.elb_name')
@when_not('aws-elb.cloud.request-sent')
def request_aws_elb_integration():
    """Request AWS integration
    """
    status_set('maintenance', 'requesting cloud integration')
    elb_name = leader_get('elb_name')
    cloud = endpoint_from_flag('endpoint.aws.joined')
    cloud.tag_instance({'juju_elb': elb_name})
    cloud.tag_instance_security_group({'juju_elb': elb_name})
    cloud.tag_instance_subnet({'juju_elb': elb_name})
    cloud.enable_acm_fullaccess()
    cloud.enable_instance_inspection()
    cloud.enable_load_balancer_management()
    cloud.enable_network_management()
    kv.set('instance_id', cloud.instance_id)
    set_state('pdl-api.cloud.request-sent')


@when('leadership.is_leader',
      'endpoint.aws.ready')
@when_not('leadership.set.vpc_id')
def set_vpc_id():
    instance = describe_instance(leader_get('instance_id'))
    leader_set(vpc_id=instance['Reservations'][0]['Instances'][0]['VpcId'])


@when('endpoint.aws.ready',
      'leadership.is_leader')
@when_not('leadership.set.cert_arn')
def initial_checks_for_fqdn_cert():
    """Set blocked status if we can't continue due to cert
    errors either on the charm config or existence of the cert 
    in the ACM itself.
    """

    elb_cert_fqdn = config('cert-fqdn')
    
    if not elb_cert_fqdn:
        status_set('blocked',
                   "Need 'fqdn-cert' configured before we can continue")
        return
    else:
        if get_cert_arn_for_fqdn(elb_cert_fqdn):
            leader_set(cert_arn=get_cert_arn_for_fqdn(elb_cert_fqdn))
        else:
            status_set('blocked', "'fqdn-cert' not found in ACM")
            return


@when('leadership.is_leader',
      'endpoint.aws-elb.available')
@when_not('leadership.set.listener_port')
def get_listener_port_from_application():
    port = endpoint_from_flag(
        'endpoint.aws-elb.available').list_unit_data()[0]
    leader_set(listener_port=port)


@when('endpoint.member.joined',
      'leadership.is_leader')
@when_not('elb.init')
def update_unitdata_kv():
    """
    This handler is ran whenever a peer is joined.
    (all node types use this handler to coordinate peers)
    """

    peers = endpoint_from_flag('endpoint.member.joined').all_units
    if len(peers) > 0 and \
       len([peer._data['private-address']
            for peer in peers if peer._data is not None]) > 0:
        kv.set('peer-nodes',
               [peer._data['private-address']
                for peer in peers if peer._data is not None])
        set_flag('elb.init')


@when('elb.init',
      'leadership.set.elb_name',
      'leadership.set.cert_arn',
      'leadership.set.vpc_id',
      'leadership.is_leader')
@when_not('leadership.set.tgt_grp_arn')
def init_elb():
    """Create the ELB, TGT, SG, and Listeners"""

    security_group_id = create_security_group_and_rule(
        name="{}-sg".format(leader_get('elb_name')),
        description="Juju created SG for {}".format(leader_get('elb_name'))
    )

    tgt_grp_arn = create_target_group(
        name="{}-tgt".format(leader_get('elb_name')),
        vpc_id=leader_get('vpc_id'),
        port=int(leader_get('listener_port')),
        health_check_path='/ping',
    )['TargetGroups'][0]['TargetGroupArn']

    elb_arn = create_elb(
        elb_name=leader_get('elb_name'),
        subnets=[],
        [security_group_id]
    )['LoadBalancers'][0]['LoadBalancerArn']

    create_listener(leader_get('cert_arn'), elb_arn, tgt_grp_arn)

    status_set('active', "ELB, TGT, SG, and Listeners initialized")
    leader_set(tgt_grp_arn=tgt_grp_arn)


@when('endpoint.aws.ready',
      'leadership.set.tgt_grp_arn')
@when_not('target.registered')
def register_with_tgt_grp():
    """Every unit will run this code to register with the 
    target group once the target group is created and the elb 
    has been initialized in init_elb().
    """
    register_target(leader_get('tgt_grp_arn'), kv.get('instance_id'))
    status_set('active', "Target registered")
    set_flag('target.registered')
