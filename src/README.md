# layer-aws-elb

This layer adds AWS ElasticLoadBalancer infront of your EC2 deployed applications.

## Usage and Caveats

To use this charm you must have a pre-existing ACM cert 
for the domain/fqdn you wish to use on the ELB, as well as pre-existing IGW subnets.

Future version of this charm will offer lets-encrypt cert creation/acquisition capability.

# Deployment Example
```bash
# Create the model and network space
# (I often use a "nat" space that includes subnets that use a routing table that points 0.0.0.0/0 -> nat-gw)

juju add-model aws-elb-testing aws/us-west-2
juju add-spaces nat 172.31.102.0/24 172.31.103.0/24 172.31.104.0/24
```
```bash
# Deploy the 2 primary charms and the subordinate
juju deploy cs:~containers/aws-integrator-5 --constraints "spaces=nat instance-type=m5.large"

juju deploy cs:~omnivector/aws-elb

juju deploy cs:~jamesbeedy/flask-test-2 --constraints "spaces=nat instance-type=m5.large"
juju expose flask-test

# Trust, config, and make relations
# (The aws-elb charm will block until the 'subnets' and 'cert-fqdn' configs are set)

juju trust aws-integrator

# (use your own cert-fqdn and subnet ids - both must pre-exist in aws)
juju config aws-elb cert-fqdn="*.peopledatalabs.com"
juju config aws-elb subnets="subnet-1de11955,subnet-50b0f336,subnet-7128282a"


juju relate aws-integrator aws-elb

juju relate aws-elb flask-test
```
After the ELB is [successfully created](https://paste.ubuntu.com/p/QzMS6fW8XK/), you can use the action `get-elb-dns` to get the dns name of the ELB.

```bash
$ juju run-action aws-elb/17 --wait get-elb-dns
unit-aws-elb-17:
  id: 6e867463-2f3b-4411-82c9-6f14b6b8f209
  results:
    elb-dns: juju-elb-a9dce8c-805899264.us-west-2.elb.amazonaws.com
  status: completed
  timing:
    completed: 2018-09-23 00:48:21 +0000 UTC
    enqueued: 2018-09-23 00:48:21 +0000 UTC
    started: 2018-09-23 00:48:21 +0000 UTC
  unit: aws-elb/17
```

Following this you need to create/update an CNAME record to point at the FQDN of the ELB before you will be able to successfully access the web endpoint.

### Copyright
* James Beedy (c) 2018 <jamesbeedy@gmail.com>

### License
* AGPLv3 (See `License' file)
