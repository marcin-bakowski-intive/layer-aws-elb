# layer-aws-elb

This layer adds AWS ElasticLoadBalancer infront of your EC2 deployed applications.

## Usage and Caveats

To use this charm you must have a pre-existing ACM cert 
for the domain/fqdn you wish to use on the ELB, as well as pre-existing IGW subnets.

Future version of this charm will offer lets-encrypt cert creation/acquisition capability.

When you create a load balancer in a VPC, you must choose whether to make it an internal load balancer 
or an Internet-facing load balancer.

The nodes of an Internet-facing load balancer have public IP addresses. The DNS name of an Internet-facing 
load balancer is publicly resolvable to the public IP addresses of the nodes. Therefore, Internet-facing 
load balancers can route requests from clients over the Internet. For more information, 
see Internet-Facing Classic Load Balancers.

The nodes of an internal load balancer have only private IP addresses. The DNS name of an internal load balancer 
is publicly resolvable to the private IP addresses of the nodes. Therefore, internal load balancers can only route
 requests from clients with access to the VPC for the load balancer.
 
It is recommended to use internal load balancer for services, which shouldn't be exposed publicly. 

# Deployment example using Internet-facing (default) ELB type
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

# Deployment example using Internal ELB type

When you use internal type ELB, you don't have to expose your juju application: `juju expose`.
Your application is available only inside your VPC. You can also launch your internal 
application EC2 instances without public IP assigned by configuring VPC subnets with 
`Auto-assign public IPv4 address` option disabled and assign your juju application 
machines to defined spaces (internal subnets).

```bash
# Create the model and network space (you can use existing model)

juju add-model aws-elb-testing aws/us-west-2
# create internal-nat space
juju add-space internal-nat 172.31.102.0/24 172.31.103.0/24 172.31.104.0/24
```

```bash
# Deploy the 2 primary charms and the subordinate
juju deploy cs:~containers/aws-integrator-5
juju deploy cs:~omnivector/aws-elb

# deploy your internal service and setup internal subnets only EC2 instances
juju deploy ./flask-internal --constraints "spaces=internal-nat"

# Trust, config, and make relations
# (The aws-elb charm will block until the 'subnets')
juju trust aws-integrator
juju relate aws-integrator aws-elb

# set ELB internal type, ELB listen port and internal subnet ids (must pre-exist in aws)
juju config aws-elb scheme=internal
juju config aws-elb listener-raw-port=8080
juju config aws-elb subnets="subnet-1de11955,subnet-50b0f336,subnet-7128282a"

juju relate aws-elb flask-internal
```
After the ELB is [successfully created], you can use the action `get-elb-dns` 
(see example above from Internet-type deployment example). ELB internal type expose service using private IP address, so the FQDN of the ELB is only reachable inside your VPC.

### Copyright
* James Beedy (c) 2018 <jamesbeedy@gmail.com>

### License
* AGPLv3 (See `License' file)
