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
    get_cert_arn_for_fqdn,
)


kv = unitdata.kv()


@hook('start')
@when_not('aws-elb.juju.started')
def set_started_flag():
    elb_uuid = os.getenv('JUJU_MODEL_UUID')[:7]
    elb_name = 'juju-elb-{}'.format(elb_uuid)
    kv.set('elb_name', elb_name)
    set_flag('aws-elb.juju.started')


@when('endpoint.aws.joined',
      'aws-elb.juju.started')
@when_not('aws-elb.cloud.request-sent')
def request_aws_elb_integration():
    """Request AWS integration
    """
    status_set('maintenance', 'requesting cloud integration')
    cloud = endpoint_from_flag('endpoint.aws.joined')
    cloud.tag_instance({'juju_elb': kv.get('elb_name')})
    cloud.tag_instance_security_group({'juju_elb': kv.get('elb_name')})
    cloud.tag_instance_subnet({'juju_elb': kv.get('elb_name')})
    cloud.enable_instance_inspection()
    cloud.enable_load_balancer_management()
    cloud.enable_network_management()
    kv.set('instance_id', cloud.instance_id)
    set_state('pdl-api.cloud.request-sent')


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
    leader_set(listener_port=endpoint_from_flag(
        'endpoint.aws-elb.available').list_unit_data()[0])
