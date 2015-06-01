from cfn_pyplates.core import CloudFormationTemplate, Mapping, Parameter, \
    Resource, Properties, DependsOn, Output
from cfn_pyplates.functions import join


AWS_REGIONS_AZ = {
    'eu-west-1': ["eu-west-1a", "eu-west-1b", "eu-west-1c"],
    'eu-central-1': ["eu-central-1a", "eu-central-1b"]
}


def get_extra_cloud_config_from_file(cloud_config_file):
    cloud_config = None
    with file(cloud_config_file) as f:
        cloud_config = f.readlines()
    return cloud_config

class BaseCFConf(object):

    def __init__(self, data):
        self.data = data


    def get_user_cloud_config(self):
        return get_extra_cloud_config_from_file('./aws/templates/users.yml')

    def _get_autoscale(
        self, name,
        extra_security_groups=[], extra_cloud_config='',
        extra_props_autoscale={},
        extra_props_launch={}, extra_attrs_launch=[],
        config_min_size=3, config_max_size=3
    ):

        # general configs
        autoscale_name = '%sServerAutoScale' % name
        autoscale_launch_config = '%sServerLaunchConfig' % name

        # autoscaling configs
        props_autoscale = {
            "AvailabilityZones": {
                "Fn::GetAZs": {"Ref": "AWS::Region"}
            },
            "LaunchConfigurationName": {
                "Ref": autoscale_launch_config
            },
            "MinSize": "%s" % config_min_size,
            "MaxSize": "%s" % config_max_size,
            "Tags": [
                {
                    "Key": "Name",
                    "Value": name,
                    "PropagateAtLaunch": True
                },
                {
                    "Key": "Role",
                    "Value": name,
                    "PropagateAtLaunch": True
                }
            ]
        }

        props_autoscale.update(extra_props_autoscale)

        # launch configs
        sec_groups = [
            {"Ref": sec_group} for sec_group in ["SSHFromBastionSecurityGroup"] + extra_security_groups
        ]

        cloud_config = self.get_user_cloud_config()
        cloud_config += extra_cloud_config

        props_launch = {
            "ImageId": {
                "Fn::FindInMap": [
                    "RegionMap",
                    {
                        "Ref": "AWS::Region"
                    },
                    name
                ]
            },
            "InstanceType": {
                "Ref": "%sInstanceType" % name
            },
            "SecurityGroups": sec_groups,
            "UserData": {
                "Fn::Base64": join('', *cloud_config)
            }
        }
        props_launch.update(extra_props_launch)

        attrs_launch = extra_attrs_launch

        return [
            Resource(
                autoscale_name,
                "AWS::AutoScaling::AutoScalingGroup",
                Properties(props_autoscale)
            ),

            Resource(
                autoscale_launch_config,
                "AWS::AutoScaling::LaunchConfiguration",
                Properties(props_launch),
                attributes=attrs_launch
            )
        ]


    def _get_mappings(self):
        return []

    def _get_resources(self):
        return []

    def _get_parameters(self):
        return []

    def _get_outputs(self):
        return []

    def _data(self):
        return {
            'mappings': self._get_mappings(),
            'resources': self._get_resources(),
            'parameters': self._get_parameters(),
            'outputs': self._get_outputs()
        }

    def add(self, cft):
        for prop, l in self._data().items():
            for val in l:
                getattr(cft, prop).add(val)
        return self.data


class GeneralCFConf(BaseCFConf):
    def _get_mappings(self):
        mapping_props = {
            "eu-central-1": {
                "nat": "ami-1e073a03",
                "SSHBastion": "ami-accff2b1"
            },
            "eu-west-1": {
                "nat": "ami-14913f63",
                "SSHBastion": "ami-47a23a30"
            }
        }

        mapping_props[self.data['region']].update({
            "CoreOS": self.data['coreos_ami'],
            "EtcdCluster": self.data['coreos_ami'],
        })
        return [
            Mapping('RegionMap', mapping_props)
        ]

    def _get_parameters(self):
        return [
            Parameter('EnvName', 'String', {
                'Description': 'Environment Name'
            }),
            Parameter(
                "SSHBastionInstanceType",
                "String",
                {
                    "Description": "SSH Bastion EC2 HVM instance type (m3.medium, etc).",
                    "Default": "t2.micro",
                    "ConstraintDescription": "Must be a valid EC2 HVM instance type."
                }
            ),
            Parameter(
                "NATInstanceType",
                "String",
                {
                    "Description": "NAT EC2 HVM instance type (m3.medium, etc).",
                    "Default": "t2.small",
                    "ConstraintDescription": "Must be a valid EC2 HVM instance type."
                }
            ),
            Parameter(
                "EtcdClusterInstanceType",
                "String",
                {
                    "Description": "EC2 HVM instance type (m3.medium, etc).",
                    "Default": "t2.micro",
                    "ConstraintDescription": "Must be a valid EC2 HVM instance type."
                }
            ),
            Parameter(
                "CoreOSInstanceType",
                "String",
                {
                    "Description": "EC2 HVM instance type (m3.medium, etc).",
                    "Default": "t2.medium",
                    "ConstraintDescription": "Must be a valid EC2 HVM instance type."
                }
            ),
            Parameter(
                "CoreOSClusterSize",
                "Number", {
                    "Default": "3",
                    "MinValue": "1",
                    "MaxValue": "12",
                    "Description": "Number of CoreOS worker nodes in cluster (1-12).",
                }
            ),
            Parameter(
                "EtcdClusterSize",
                "Number", {
                    "Default": "3",
                    "MinValue": "1",
                    "MaxValue": "12",
                    "Description": "Number of CoreOS service nodes in cluster (etcd cluster) (1-12).",
                }
            ),
            Parameter(
                "DiscoveryURL",
                "String", {
                    "Description": "An unique etcd cluster discovery URL. Grab a new token from https://discovery.etcd.io/new",
                }
            ),
            Parameter(
                "DBAllocatedStorage",
                "Number", {
                    "Description": "Allocated DB storage (in GB)",
                    "Default": "10",
                }
            ),
            Parameter(
                "DBInstanceClass",
                "String", {
                    "Description": "RDS instance type",
                    "Default": "db.t2.small",
                }
            ),
            Parameter(
                "DBUsername",
                "String", {
                    "Description": "Database username",
                }
            ),
            Parameter(
                "DBPassword",
                "String", {
                    "Description": "Database username",
                }
            ),
            Parameter(
                "DBName",
                "String", {
                    "Description": "Database name",
                }
            )
        ]

    def _get_resources(self):
        return [
            Resource(
                "PublicHTTPSecurityGroup",
                "AWS::EC2::SecurityGroup",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "GroupDescription": "Ingress for port 80 from anywhere",
                    "SecurityGroupIngress": [
                        {
                            "CidrIp": "0.0.0.0/0",
                            "IpProtocol": "tcp",
                            "FromPort": "80",
                            "ToPort": "80"
                        }
                    ],
                    "Tags": [
                        {"Key": "Name", "Value": "PublicHTTPSecurityGroup"}
                    ]
                })
            ),
            Resource(
                "SSHBastionSecurityGroup",
                "AWS::EC2::SecurityGroup",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "GroupDescription": "Ingress for SSH from anywhere",
                    "SecurityGroupIngress": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": "22",
                            "ToPort": "22",
                            "CidrIp": "0.0.0.0/0"
                        }
                    ],
                    "Tags": [
                        {"Key": "Name", "Value": "SSHBastionSecurityGroup"}
                    ]
                })
            ),
            Resource(
                "SSHFromBastionSecurityGroup",
                "AWS::EC2::SecurityGroup",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "GroupDescription": "SSH from SSH Bastion SecurityGroup",
                    "SecurityGroupIngress": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": "22",
                            "ToPort": "22",
                            "SourceSecurityGroupId": {"Ref": "SSHBastionSecurityGroup"}
                        }
                    ],
                    "Tags": [
                        {"Key": "Name", "Value": "SSHFromBastionSecurityGroup"}
                    ]
                })
            ),
            Resource(
                "SQSUser",
                "AWS::IAM::User",
                Properties({
                    "Policies":
                        [{
                             "PolicyName": "AmazonSQSFullAccess",
                             "PolicyDocument": {
                                 "Version": "2012-10-17",
                                 "Statement":
                                     [{
                                          "Effect": "Allow",
                                          "Action": [
                                              "sqs:*"
                                          ],
                                          "Resource": "*"
                                      }]
                             }
                         }]
                }
            )),
            Resource(
                "SQSAccessKey",
                "AWS::IAM::AccessKey",
                Properties({
                    "UserName" : { "Ref" : "SQSUser" }
                })
            )
        ]

    def _get_outputs(self):
        return [
            Output(
                "Region",
                {"Ref": "AWS::Region"},
                "AWS Region"
            ),
            Output(
                "SQSAccessKey",
                {"Ref" : "SQSAccessKey" },
                "SQS Access Key"
            ),
            Output(
                "SQSSecretKey",
                {"Fn::GetAtt" : [ "SQSAccessKey", "SecretAccessKey" ]},
                "SQS Secret Key"
            )
        ]


class SubnetsCFConf(BaseCFConf):
    def _get_mappings(self):
        mapping_props = {
            "VPC": {"CIDR": "10.0.0.0/16"},
        }

        self.data['public_subnets'] = []
        self.data['private_subnets'] = []

        for index, az in enumerate(AWS_REGIONS_AZ.get(self.data['region']), start=1):
            public_subnet_name = 'PublicSubnet%s' % index
            private_subnet_name = 'PrivateSubnet%s' % index

            mapping_props[public_subnet_name] = {
                "CIDR": "10.0.%s.0/24" % (index-1),
                "AZ": az
            }
            mapping_props[private_subnet_name] = {
                "CIDR": "10.0.%s.0/24" % (100+index-1),
                "AZ": az
            }

            # add subnet names to data
            self.data['public_subnets'].append(public_subnet_name)
            self.data['private_subnets'].append(private_subnet_name)

        return [
            Mapping('SubnetConfig', mapping_props)
        ]

    def _get_public_subnets(self):
        resources = [
            Resource(
                "PublicRouteTable",
                "AWS::EC2::RouteTable",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "Tags": [
                        {"Key": "Application", "Value": {"Ref": "AWS::StackId"}}
                    ]
                })
            ),

            Resource(
                "PublicRoute",
                "AWS::EC2::Route",
                Properties({
                    "RouteTableId": {"Ref": "PublicRouteTable"},
                    "DestinationCidrBlock": "0.0.0.0/0",
                    "GatewayId": {"Ref": "InternetGateway"}
                }), attributes=[
                    DependsOn("GatewayToInternet")
                ]
            ),
        ]

        for subnet_name in self.data['public_subnets']:
            table_association_name = "%sRouteTableAssociation" % subnet_name

            resources += [
                Resource(
                    subnet_name,
                    "AWS::EC2::Subnet",
                    Properties({
                        "VpcId": {"Ref": "VPC"},
                        "AvailabilityZone": {
                            "Fn::FindInMap": ["SubnetConfig", subnet_name, "AZ"]
                        },
                        "CidrBlock": {
                            "Fn::FindInMap": ["SubnetConfig", subnet_name, "CIDR"]
                        },
                        "Tags": [
                            {"Key": "Application", "Value": {"Ref": "AWS::StackId"}},
                            {"Key": "Network", "Value": subnet_name}
                        ]
                    })
                ),

                Resource(
                    table_association_name,
                    "AWS::EC2::SubnetRouteTableAssociation",
                    Properties({
                        "SubnetId": {"Ref": subnet_name},
                        "RouteTableId": {"Ref": "PublicRouteTable"}
                    })
                ),
            ]
        return resources

    def _get_private_subnets(self):
        resources = [
            Resource(
                "PrivateRouteTable",
                "AWS::EC2::RouteTable",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "Tags": [
                        {"Key": "Name", "Value": "PrivateRouteTable"}
                    ]
                })
            ),
            Resource(
                "PrivateInternetRoute",
                "AWS::EC2::Route",
                Properties({
                    "RouteTableId": {"Ref": "PrivateRouteTable"},
                    "DestinationCidrBlock": "0.0.0.0/0",
                    "InstanceId": {
                        "Ref": "NATInstance"
                    }
                }), attributes=[
                    DependsOn("NATInstance")
                ]
            ),
        ]

        for subnet_name in self.data['private_subnets']:
            table_association_name = "%sRouteTableAssociation" % subnet_name

            resources += [
                Resource(
                    subnet_name,
                    "AWS::EC2::Subnet",
                    Properties({
                        "VpcId": {"Ref": "VPC"},
                        "AvailabilityZone": {
                            "Fn::FindInMap": ["SubnetConfig", subnet_name, "AZ"]
                        },
                        "CidrBlock": {
                            "Fn::FindInMap": ["SubnetConfig", subnet_name, "CIDR"]
                        },
                        "Tags": [
                            {"Key": "Application", "Value": {"Ref": "AWS::StackId"}},
                            {"Key": "Network", "Value": subnet_name}
                        ]
                    })
                ),

                Resource(
                    table_association_name,
                    "AWS::EC2::SubnetRouteTableAssociation",
                    Properties({
                        "SubnetId": {"Ref": subnet_name},
                        "RouteTableId": {"Ref": "PrivateRouteTable"}
                    })
                ),
            ]
        return resources

    def _get_resources(self):
        resources = [
            Resource(
                "VPC",
                "AWS::EC2::VPC",
                Properties({
                    "CidrBlock": {
                        "Fn::FindInMap": ["SubnetConfig", "VPC", "CIDR"]
                    },
                    "EnableDnsSupport": "true",
                    "EnableDnsHostnames": "true",
                    "Tags": [
                        {"Key": "Application", "Value": {"Ref": "AWS::StackId"}}
                    ]
                })
            ),

            Resource(
                "InternetGateway",
                "AWS::EC2::InternetGateway",
                Properties({
                    "Tags": [
                        {"Key": "Application", "Value": {"Ref": "AWS::StackId"}}
                    ]
                })
            ),

            Resource(
                "GatewayToInternet",
                "AWS::EC2::VPCGatewayAttachment",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "InternetGatewayId": {"Ref": "InternetGateway"}
                })
            )
        ]

        resources += self._get_public_subnets()
        resources += self._get_private_subnets()

        return resources


class NATCFConf(BaseCFConf):

    def _get_resources(self):
        return [
            Resource(
                "NATSecurityGroup",
                "AWS::EC2::SecurityGroup",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "GroupDescription": "NAT Instance Security Group",
                    "SecurityGroupIngress": [
                        {
                            "IpProtocol": "icmp",
                            "FromPort": "-1",
                            "ToPort": "-1",
                            "CidrIp": "10.0.0.0/16"
                        },
                        {
                            "IpProtocol": "tcp",
                            "FromPort": "0",
                            "ToPort": "65535",
                            "CidrIp": "10.0.0.0/16"
                        }
                    ],
                    "Tags": [
                        {"Key": "Name", "Value": "NATSecurityGroup"}
                    ]
                })
            ),
            Resource(
                "NATInstance",
                "AWS::EC2::Instance",
                Properties({
                    "ImageId": {
                        "Fn::FindInMap": [
                            "RegionMap",
                            {
                                "Ref": "AWS::Region"
                            },
                            "nat"
                        ]
                    },
                    "InstanceType": {
                        "Ref": "NATInstanceType"
                    },
                    "BlockDeviceMappings": [
                        {
                            "DeviceName": "/dev/xvda",
                            "Ebs": {
                                "VolumeSize": 10
                            }
                        }
                    ],
                    "NetworkInterfaces": [
                        {
                            "GroupSet": [
                                {"Ref": "NATSecurityGroup"},
                                {"Ref": "SSHFromBastionSecurityGroup"}
                            ],
                            "SubnetId": {
                                "Ref": self.data['public_subnets'][0]
                            },
                            "AssociatePublicIpAddress": "true",
                            "DeviceIndex": "0",
                            "DeleteOnTermination": "true"
                        }
                    ],
                    "SourceDestCheck": "false",
                    "Tags": [
                        {"Key": "Name", "Value": "NATHost"},
                        {"Key": "Role", "Value": "NAT"}
                    ],
                    "UserData": {
                        "Fn::Base64": {
                            "Fn::Join": [
                                "",
                                self.get_user_cloud_config()
                            ]
                        }
                    }
                }),
                attributes=[
                    DependsOn("GatewayToInternet")
                ]
            )
        ]


class SSHBastionCFConf(BaseCFConf):
    def _get_resources(self):
        resources = self._get_autoscale(
            'SSHBastion',
            extra_props_autoscale={
                "VPCZoneIdentifier": [
                    {"Ref": subnet_name} for subnet_name in self.data['public_subnets']
                ],
            },
            extra_props_launch={
                "AssociatePublicIpAddress": "true",
                "BlockDeviceMappings": [
                    {
                        "DeviceName": "/dev/xvda",
                        "Ebs": {
                            "VolumeSize": 10
                        }
                    }
                ]
            },
            extra_attrs_launch=[
                DependsOn("GatewayToInternet")
            ],
            extra_security_groups=['SSHBastionSecurityGroup']
        )
        return resources


class CoreOSCFConf(BaseCFConf):
    """
        cloud-config details here: https://github.com/coreos/coreos-cloudinit/blob/master/Documentation/cloud-config.md
        more etcd2 configs here: https://github.com/coreos/etcd/blob/86e616c6e974828fc9119c1eb0f6439577a9ce0b/Documentation/configuration.md
        more fleet configs here: https://github.com/coreos/fleet/blob/master/fleet.conf.sample
    """

    def _get_etcd_cluster_resources(self):
        resources = self._get_autoscale(
            'EtcdCluster',
            extra_security_groups=['CoreOSSecurityGroup'],
            extra_cloud_config=[
                "coreos:\n",
                "  update:\n",
                "    reboot-strategy: etcd-lock\n",
                "  etcd2:\n",
                "    discovery: ", {"Ref": "DiscoveryURL"}, "\n",
                "    advertise-client-urls: http://$private_ipv4:2379\n",
                "    initial-advertise-peer-urls: http://$private_ipv4:2380\n",
                "    listen-client-urls: http://0.0.0.0:2379\n",
                "    listen-peer-urls: http://$private_ipv4:2380\n",
                "  fleet:\n",
                "    metadata: \"role=services\"\n",
                "    etcd_servers: http://127.0.0.1:2379\n"
                "  units:\n",
                "    - name: etcd2.service\n",
                "      command: start\n",
                "    - name: fleet.service\n",
                "      command: start\n"
            ],
            config_min_size=1,
            config_max_size=12,
            extra_props_autoscale={
                "VPCZoneIdentifier": [
                    {"Ref": subnet_name} for subnet_name in self.data['private_subnets']
                ],
                "DesiredCapacity": {
                    "Ref": "EtcdClusterSize"
                }
            }
        )

        return resources

    def _get_coreos_resources(self):
        resources = self._get_autoscale(
            'CoreOS',
            extra_security_groups=['CoreOSSecurityGroup', 'WebAppSecurityGroup'],
            extra_cloud_config=[
                "coreos:\n",
                "  etcd2:\n",
                "    discovery: ", {"Ref": "DiscoveryURL"}, "\n",
                "    proxy: on\n",
                "    listen-client-urls: http://0.0.0.0:2379\n"
                "  fleet:\n",
                "    metadata: \"role=worker\"\n",
                "    etcd_servers: http://127.0.0.1:2379\n",
                "  flannel:\n",
                "    etcd_endpoints: http://127.0.0.1:2379\n",
                "  units:\n",
                "    - name: etcd2.service\n",
                "      command: start\n",
                "    - name: fleet.service\n",
                "      command: start\n",
                "    - name: flanneld.service\n",
                "      drop-ins:\n",
                "      - name: 50-network-config.conf\n",
                "        content: |\n",
                "          [Unit]\n",
                "          Requires=etcd2.service\n",
                "          [Service]\n",
                "          ExecStartPre=/usr/bin/etcdctl set /coreos.com/network/config '{ \"Network\": \"192.168.192.0/18\", \"Backend\": {\"Type\": \"vxlan\"}}'\n",
                "      command: start\n"
            ],
            config_min_size=1,
            config_max_size=12,
            extra_props_autoscale={
                "VPCZoneIdentifier": [
                    {"Ref": subnet_name} for subnet_name in self.data['private_subnets']
                ],
                "DesiredCapacity": {
                    "Ref": "CoreOSClusterSize"
                }
            }
        )

        resources.append(
            Resource(
                "WebAppSecurityGroup",
                "AWS::EC2::SecurityGroup",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "GroupDescription": "WebApp SecurityGroup",
                    "SecurityGroupIngress": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": "8080",
                            "ToPort": "8080",
                            "SourceSecurityGroupId": {"Ref": "NATSecurityGroup"}
                        },
                        {
                            "IpProtocol": "tcp",
                            "FromPort": "8080",
                            "ToPort": "8080",
                            "SourceSecurityGroupId": {"Ref": "PublicHTTPSecurityGroup"}
                        }
                    ],
                    "Tags": [
                        {"Key": "Name", "Value": "WebAppSecurityGroup"}
                    ]
                })
            )
        )
        return resources

    def _get_resources(self):
        resources = [
            Resource(
                "CoreOSSecurityGroup",
                "AWS::EC2::SecurityGroup",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "GroupDescription": "CoreOS SecurityGroup",
                    "SecurityGroupIngress": [
                        {
                            "CidrIp": "10.0.0.0/16",
                            "IpProtocol": "udp",
                            "FromPort": "0",
                            "ToPort": "65535"
                        },
                        {
                            "CidrIp": "10.0.0.0/16",
                            "IpProtocol": "icmp",
                            "FromPort": "-1",
                            "ToPort": "-1"
                        }
                    ],
                    "Tags": [
                        {"Key": "Name", "Value": "CoreOSSecurityGroup"}
                    ]
                })
            ),
            Resource(
                "CoreOSSecurityGroup2380Ingress",
                "AWS::EC2::SecurityGroupIngress",
                Properties({
                    "GroupId": {"Ref": "CoreOSSecurityGroup"},
                    "IpProtocol": "tcp",
                    "FromPort": "2380",
                    "ToPort": "2380",
                    # "SourceSecurityGroupId": {"Ref": "CoreOSSecurityGroup"}  # TODO not working for now because need to use fleetctl locally to load units
                    "CidrIp": "10.0.0.0/16"
                }), attributes=[
                    DependsOn("CoreOSSecurityGroup")
                ]
            ),
            Resource(
                "CoreOSSecurityGroup2379Ingress",
                "AWS::EC2::SecurityGroupIngress",
                Properties({
                    "GroupId": {"Ref": "CoreOSSecurityGroup"},
                    "IpProtocol": "tcp",
                    "FromPort": "2379",
                    "ToPort": "2379",
                    # "SourceSecurityGroupId": {"Ref": "CoreOSSecurityGroup"}  # TODO not working for now because need to use fleetctl locally to load units
                    "CidrIp": "10.0.0.0/16"
                }), attributes=[
                    DependsOn("CoreOSSecurityGroup")
                ]
            )
        ]

        resources += self._get_etcd_cluster_resources()
        resources += self._get_coreos_resources()
        return resources


class DBCFConf(BaseCFConf):
    def _get_resources(self):
        return [
            Resource(
                "MasterDBSubnetGroup",
                "AWS::RDS::DBSubnetGroup",
                Properties({
                    "DBSubnetGroupDescription": "Master DB subnet group",
                    "SubnetIds": [
                        {"Ref": subnet_name} for subnet_name in self.data['private_subnets']
                    ]
                })
            ),

            Resource(
                "MasterDBSecurityGroup",
                "AWS::EC2::SecurityGroup",
                Properties({
                    "VpcId": {"Ref": "VPC"},
                    "GroupDescription": "Ingress for CoreOS instance security group",
                    "SecurityGroupIngress": [
                        {
                            "SourceSecurityGroupId": {"Ref": "CoreOSSecurityGroup"},
                            "IpProtocol": "tcp",
                            "FromPort": "5432",
                            "ToPort": "5432"
                        }
                    ],
                    "Tags": [
                        {"Key": "Name", "Value": "MasterDBSecurityGroup"}
                    ]
                })
            ),

            Resource(
                "PrimaryDB",
                "AWS::RDS::DBInstance",
                Properties({
                    "DBName": {"Ref": "DBName"},
                    "AllocatedStorage": {"Ref": "DBAllocatedStorage"},
                    "DBInstanceClass": {"Ref": "DBInstanceClass"},
                    "Engine": "postgres",
                    "EngineVersion": "9.3.5",
                    "MasterUsername": {"Ref": "DBUsername"},
                    "MasterUserPassword": {"Ref": "DBPassword"},
                    "Port": "5432",
                    "VPCSecurityGroups": [{"Ref": "MasterDBSecurityGroup"}],
                    "PubliclyAccessible": "false",
                    "PreferredMaintenanceWindow": "sun:12:00-sun:12:30",
                    "PreferredBackupWindow": "23:00-23:30",
                    "BackupRetentionPeriod": "7",
                    "DBParameterGroupName": "default.postgres9.3",
                    "AutoMinorVersionUpgrade": "true",
                    "MultiAZ": "false",
                    "DBSubnetGroupName": {"Ref": "MasterDBSubnetGroup"},
                    "Tags": [{"Key": "Role", "Value": "Primary"}]
                })
            )
        ]

    def _get_outputs(self):
        return [
            Output(
                "PrimaryDBHostname",
                {"Fn::GetAtt": ["PrimaryDB", "Endpoint.Address"]},
                "Primary Database Hostname",
            ),
            Output(
                "PrimaryDBPort",
                {"Fn::GetAtt": ["PrimaryDB", "Endpoint.Port"]},
                "Primary Database Port"
            )
        ]


class ELBCFConf(BaseCFConf):
    def _get_resources(self):
        return [
            Resource(
                "PublicELB",
                "AWS::ElasticLoadBalancing::LoadBalancer",
                Properties({
                    "Subnets": [
                        {"Ref": subnet_name} for subnet_name in self.data['public_subnets']
                    ],
                    "SecurityGroups": [
                        {"Ref": "PublicHTTPSecurityGroup"}
                    ],
                    "Listeners": [{
                        "LoadBalancerPort": "80",
                        "InstancePort": "8080",
                        "Protocol": "HTTP"
                    }],
                    "HealthCheck": {
                        "Target": "HTTP:8080/",
                        "HealthyThreshold": "3",
                        "UnhealthyThreshold": "5",
                        "Interval": "30",
                        "Timeout": "5"
                    }
                })
            ),

            Resource(
                "PublicELBIAMUser",
                "AWS::IAM::User",
                Properties({
                    "Policies": [{
                        "PolicyName": "PublicELBRegisterDeregisterOnly",
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [{
                                "Effect": "Allow",
                                "Action": [
                                    "elasticloadbalancing:DeregisterInstancesFromLoadBalancer",
                                    "elasticloadbalancing:RegisterInstancesWithLoadBalancer"
                                ],
                                "Resource": {
                                    "Fn::Join": [
                                        "",
                                        [
                                            "arn:aws:elasticloadbalancing:",
                                            {
                                                "Ref": "AWS::Region"
                                            },
                                            ":",
                                            {
                                                "Ref": "AWS::AccountId"
                                            },
                                            ":loadbalancer/",
                                            {
                                                "Ref": "PublicELB"
                                            }
                                        ]
                                    ]
                                }
                            }]
                        }
                    }]
                })
            ),

            Resource(
                "PublicELBAccessKey",
                "AWS::IAM::AccessKey",
                Properties({
                    "UserName": {"Ref": "PublicELBIAMUser"}
                })
            )
        ]

    def _get_outputs(self):
        return [
            Output(
                "PublicELBName",
                {"Ref": "PublicELB"},
                "Public ELB Name"
            ),
            Output(
                "PublicELBAccessKey",
                {"Ref": "PublicELBAccessKey"},
                "Public ELB ACCESS_KEY"
            ),
            Output(
                "PublicELBSecretAccessKey",
                {"Fn::GetAtt": ["PublicELBAccessKey", "SecretAccessKey"]},
                "Public ELB SECRET_ACCESS_KEY"
            )
        ]


class PublicELBDNSConfs(BaseCFConf):
    DNS_MAPPING = ('', 'next', 'previous')

    def _get_dns_record_name(self, prefix):
        return "Public%sELBDNSRecord" % prefix.title()

    def _get_resources(self):
        resources = []
        dns_suffix = self.data['dns_suffix']
        for prefix in self.DNS_MAPPING:
            name = self._get_dns_record_name(prefix)

            if prefix != '':
                prefix = "%s." % prefix

            resources.append(
                Resource(
                    name,
                    "AWS::Route53::RecordSet",
                    Properties({
                        "HostedZoneName": dns_suffix,
                        "Comment": "DNS name for TeamCity",
                        "Name": {
                            "Fn::Join": ["", [
                                prefix,
                                {"Ref": "EnvName"},
                                '.',
                                dns_suffix
                            ]]
                        },
                        "Type": "CNAME",
                        "TTL": "60",
                        "ResourceRecords": [
                            {"Fn::GetAtt": ["PublicELB",
                                            "CanonicalHostedZoneName"]}
                        ]
                    })
                )
            )
        return resources

    def _get_outputs(self):
        outputs = []
        for prefix in self.DNS_MAPPING:
            name = self._get_dns_record_name(prefix)

            outputs.append(
                Output(
                    name,
                    {"Ref": name},
                    name
                )
            )
        return outputs


CONFIGs = [
    GeneralCFConf, SubnetsCFConf, NATCFConf, SSHBastionCFConf,
    CoreOSCFConf, DBCFConf, ELBCFConf, PublicELBDNSConfs
]


def get_template(region, coreos_ami, dns_suffix):
    cft = CloudFormationTemplate(
        description='Core OS on EC2 app cluster'
    )

    data = {
        'region': region,
        'coreos_ami': coreos_ami,
        'dns_suffix': dns_suffix
    }

    for Conf in CONFIGs:
        data.update(
            Conf(data=data).add(cft)
        )
    return cft
