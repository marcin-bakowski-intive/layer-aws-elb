# layer-aws-elb

This layer adds AWS ElasticLoadBalancer infront of your EC2 deployed applications.

## Usage and Caveats

To use this charm you must have a pre-existing ACM cert 
for the domain/fqdn you wish to use on the ELB.

Future version of this charm will offer lets-encrypt cert creation/acquisition capability.

1. Deploy this charm and relate it to the `aws-integrator` charm.

```bash
juju deploy cs:~containers/aws-integrator-5
juju deploy cs:~omnivector/aws-elb

juju relate aws-integrator aws-elb
```
Ensure to `trust` the `aws-integrator` charm.
```bash
juju trust aws-integrator
```

2. Deploy a charm with an http endpoint that implements the `aws-elb` provides interface.
```bash
juju deploy cs:~jamesbeedy/flask-test-0 -n 3
```

3. Relate the http endpoint charm to the `aws-elb`.
```bash
juju relate aws-elb flask-test
```

4. Add the `cert-fqdn` config.
This charm will block until you configure an fqdn that matches the domain for a pre-existing cert in ACM.
```bash
juju config aws-elb cert-fqdn="*.example.com"
```

## Access and Archival
This layer should be found as a built charm in the charmstore
in the Omnivector namespace [https://jujucharms.com/u/omnivector](https://jujucharms.com/u/omnivector)

