import boto3
import os

def aws_resource(service):
    if os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY'):
        return boto3.resource(
            service,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name='us-west-2')
    else:
        return boto3.resource(service)


def aws(service):
    if os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY'):
        return boto3.client(
            service,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))
    else:
        return boto3.client(service)



def create_elb(name, subnets, security_groups):
    return aws('elbv2').create_load_balancer(
        Name=name,
        Subnets=subnets,
        SecurityGroups=security_groups,
        Scheme='internet-facing',
        Type='application',
        IpAddressType='ipv4',
    )




def create_target_group(name, vpc_id, protocol='HTTP', port=80, health_check_path='/'):
    return aws('elbv2').create_target_group(
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


def create_security_group_and_rule(name, description, vpc_id):
    sec_group = aws_resource("ec2").create_security_group(
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


def describe_instance(instance_id):
    return aws('ec2').describe_instances(InstanceIds=[instance_id])


def get_cert_arn_for_fqdn(fqdn):
    for cert in aws('acm').list_certificates()['CertificateSummaryList']:
        if fqdn == cert['DomainName']:
            return cert['CertificateArn']
    return None


def register_target(target_group_arn, instance_id):
    return aws('elbv2').register_targets(
        TargetGroupArn=target_group_arn,Targets=[{'Id': instance_id}])
