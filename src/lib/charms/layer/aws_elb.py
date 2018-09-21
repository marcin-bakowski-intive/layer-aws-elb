import boto3
import os


def aws_resource(service, region_name=None):
    if os.getenv('AWS_ACCESS_KEY_ID') and \
       os.getenv('AWS_SECRET_ACCESS_KEY') and \
       os.getenv('AWS_REGION'):
        return boto3.resource(
            service,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
    else:
        return boto3.resource(service, region_name=region_name)


def aws(service, region_name=None):
    if os.getenv('AWS_ACCESS_KEY_ID') and \
       os.getenv('AWS_SECRET_ACCESS_KEY') and \
       os.getenv('AWS_REGION'):
        return boto3.client(
            service,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
    else:
        return boto3.client(service, region_name=region_name)


def create_elb(name, subnets, security_groups, region_name):
    return aws('elbv2', region_name).create_load_balancer(
        Name=name,
        Subnets=subnets,
        SecurityGroups=security_groups,
        Scheme='internet-facing',
        Type='application',
        IpAddressType='ipv4',
    )


def create_target_group(name, vpc_id, region_name, protocol='HTTP', port=80,
                        health_check_path='/'):
    return aws('elbv2', region_name).create_target_group(
        Name=name,
        Protocol=protocol,
        Port=port,
        VpcId=vpc_id,
        HealthCheckProtocol=protocol,
        HealthCheckPort=str(port),
        HealthCheckPath=health_check_path,
        HealthCheckIntervalSeconds=9,
        HealthCheckTimeoutSeconds=3,
        HealthyThresholdCount=9,
        UnhealthyThresholdCount=9,
        Matcher={
            'HttpCode': '200'
        },
        TargetType='instance'
    )


def create_listener(cert_arn, load_balancer_arn,
                    target_group_arn, region_name):
    return aws('elbv2', region_name).create_listener(
        LoadBalancerArn=load_balancer_arn,
        Protocol='HTTPS',
        Port=443,
        Certificates=[
            {
                'CertificateArn': cert_arn,
            },
        ],
        DefaultActions=[
            {
                'Type': 'forward',
                'TargetGroupArn': target_group_arn,
            },
        ]
    )


def create_security_group_and_rule(name, description, vpc_id, region_name):
    sec_group = \
        aws_resource("ec2", region_name=region_name).create_security_group(
            GroupName=name,
            Description=description,
            VpcId=vpc_id
        )

    sec_group.authorize_ingress(
        CidrIp='0.0.0.0/0',
        IpProtocol='tcp',
        FromPort=443,
        ToPort=443
    )
    return sec_group.id


def delete_load_balancer(elb_arn, region_name):
    return aws('elbv2', region_name).delete_load_balancer(
         LoadBalancerArn=elb_arn
    )


def delete_target_group(target_group_arn, region_name):
    return aws('elbv2', region_name).delete_target_group(
         TargetGroupArn=target_group_arn
    )


def delete_listener(listener_arn, region_name):
    return aws('elbv2', region_name).delete_listener(
         ListenerArn=listener_arn
    )


def delete_security_group(security_group_id, region_name):
    ec2 = aws_resource('ec2', region_name)
    security_group = ec2.SecurityGroup(security_group_id)

    try:
        security_group.delete()
    except Exception as e:
        print(e)
        print("{0} requires manual remediation.".format(
            security_group.group_name))


def describe_instance(instance_id, region_name):
    return aws('ec2', region_name=region_name).describe_instances(
        InstanceIds=[instance_id]
    )


def deregister_targets(targets, target_group_arn, region_name):
    aws('elbv2', region_name).deregister_targets(
        TargetGroupArn=target_group_arn,
        Targets=[{'Id': target} for target in targets],
    )


def describe_target_group(target_group_arn, region_name):
    return aws('elbv2', region_name=region_name).describe_target_health(
        TargetGroupArn=target_group_arn
    )


def get_cert_arn_for_fqdn(fqdn, region_name):
    acm = aws('acm', region_name=region_name)
    for cert in acm.list_certificates()['CertificateSummaryList']:
        if fqdn == cert['DomainName']:
            return cert['CertificateArn']
    return None


def get_elb_status(elb_arn, region_name):
    return aws('elbv2', region_name=region_name).describe_load_balancers(
        LoadBalancerArns=[elb_arn]
    )['LoadBalancers'][0]['State']['Code']


def get_elb_dns(elb_arn, region_name):
    return aws('elbv2', region_name=region_name).describe_load_balancers(
        LoadBalancerArns=[elb_arn]
    )['LoadBalancers'][0]['DNSName']


def get_targets(target_group_arn, region_name):
    targets = describe_target_group(target_group_arn, region_name)
    if len(targets['TargetHealthDescriptions']) > 0:
        return [target['Target']['Id'] for target
                in targets['TargetHealthDescriptions']]
    else:
        return []


def get_targets_health(target_group_arn, region_name):
    targets = describe_target_group(
        target_group_arn,
        region_name
    )['TargetHealthDescriptions']

    if len(targets) > 0:
        return [target['Target']['TargetHealth']['State']
                for target in targets]
    else:
        return []


def get_elb_listener_arns(elb_arn, region_name):
    listeners = aws('elbv2', region_name=region_name).describe_listeners(
        LoadBalancerArn=elb_arn
    )['Listeners']
    if len(listeners) > 0:
        return [listener['ListenerArn'] for listener in listeners]
    else:
        return []


def register_target(target_group_arn, instance_id, region_name):
    return aws('elbv2', region_name=region_name).register_targets(
        TargetGroupArn=target_group_arn,
        Targets=[{'Id': instance_id}]
    )


def set_elb_subnets(elb_arn, subnets, region_name):
    return aws('elbv2', region_name=region_name).set_subnets(
        LoadBalancerArn=elb_arn,
        Subnets=subnets
    )
