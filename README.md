# layer-aws-elb

This layer adds AWS ElasticLoadBalancer infront of your EC2 deployed applications.

## Usage and Caveats

To use this charm, your application must meet the following minimum requirements.
1. Be deployed to > 1 EC2 instances on AWS occupying at least 2 different subnets, each in a different AZ.
2. Already have a cert for the domain/fqdn you wish to use on the ELB available in ACM.
3. Meet the requirements of the AWS integratoer charm.


So long as the aforementioned requirements are met, you should have a successful experience using this software.

This subordinate charm will relate to both the aws-integrator charm and your application charm. Thus, your application charm must require the aws-elb-interface.


## Access and Archival
This layer should be built, and stored as a built charm in the charmstore
in the Omnivector namespace [https://jujucharms.com/u/omnivector](https://jujucharms.com/u/omnivector)

