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


def get_cert_arn_for_fqdn(fqdn):
    for cert in aws('acm').list_certificates()['CertificateSummaryList']:
        if fqdn == cert['DomainName']:
            return cert['CertificateArn']
    return None
