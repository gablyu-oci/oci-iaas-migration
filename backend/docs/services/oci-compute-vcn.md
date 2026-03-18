---
title: "Details for the Core Services"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm"
fetched: "20260306T012137Z"
---

`CreateVolumeBackupPolicy`

BACKUP\_POLICIES\_CREATE

`DeleteVolumeBackupPolicy`

BACKUP\_POLICIES\_DELETE

`GetVolumeBackupPolicy`

BACKUP\_POLICIES\_INSPECT

`ListVolumeBackupPolicies`

BACKUP\_POLICIES\_INSPECT

`CreateVolumeBackupPolicyAssignment`

BACKUP\_POLICY\_ASSIGNMENT\_CREATE

`DeleteVolumeBackupPolicyAssignment`

BACKUP\_POLICY\_ASSIGNMENT\_DELETE

`GetVolumeBackupPolicyAssetAssignment`

BACKUP\_POLICY\_ASSIGNMENT\_INSPECT and VOLUME\_INSPECT

`GetVolumeBackupPolicyAssignment`

BACKUP\_POLICY\_ASSIGNMENT\_INSPECT

`CreateComputeCapacityReport`

COMPUTE\_CAPACITY\_REPORT\_CREATE

`ListClusterNetworks`

CLUSTER\_NETWORK\_INSPECT and INSTANCE\_POOL\_INSPECT

`ListClusterNetworkInstances`

CLUSTER\_NETWORK\_READ and INSTANCE\_POOL\_READ

`GetClusterNetwork`

CLUSTER\_NETWORK\_READ and INSTANCE\_POOL\_READ

`UpdateClusterNetwork`

CLUSTER\_NETWORK\_UPDATE

`CreateClusterNetwork`

CLUSTER\_NETWORK\_CREATE and INSTANCE\_POOL\_CREATE

`ChangeClusterNetworkCompartment`

CLUSTER\_NETWORK\_MOVE

`TerminateClusterNetwork`

CLUSTER\_NETWORK\_DELETE and INSTANCE\_POOL\_DELETE

`ListConsoleHistories`

CONSOLE\_HISTORY\_READ and INSTANCE\_INSPECT

`CreateComputeCluster`

COMPUTE\_CLUSTER\_CREATE

`ListComputeClusters`

COMPUTE\_CLUSTER\_INSPECT

`GetComputeCluster`

COMPUTE\_CLUSTER\_READ

`UpdateComputeCluster`

COMPUTE\_CLUSTER\_UPDATE

`ChangeComputeClusterCompartment`

COMPUTE\_CLUSTER\_MOVE

`DeleteComputeCluster`

COMPUTE\_CLUSTER\_DELETE

`ListConsoleHistories`

CONSOLE\_HISTORY\_READ and INSTANCE\_INSPECT

`GetConsoleHistory`

CONSOLE\_HISTORY\_READ and INSTANCE\_INSPECT

`ShowConsoleHistoryData`

CONSOLE\_HISTORY\_READ and INSTANCE\_READ and INSTANCE\_IMAGE\_READ

`CaptureConsoleHistory`

CONSOLE\_HISTORY\_CREATE and INSTANCE\_READ and INSTANCE\_IMAGE\_READ

`DeleteConsoleHistory`

CONSOLE\_HISTORY\_DELETE

`ListCpes`

CPE\_READ

`GetCpe`

CPE\_READ

`UpdateCpe`

CPE\_UPDATE

`CreateCpe`

CPE\_CREATE

`DeleteCpe`

CPE\_DELETE

`ChangeCpeCompartment`

CPE\_RESOURCE\_MOVE

`UpdateTunnelCpeDeviceConfig`

IPSEC\_CONNECTION\_UPDATE

`GetTunnelCpeDeviceConfig`

IPSEC\_CONNECTION\_READ

`GetTunnelCpeDeviceTemplateContent`

IPSEC\_CONNECTION\_READ

`GetCpeDeviceTemplateContent`

IPSEC\_CONNECTION\_READ

`GetIpsecCpeDeviceTemplateContent`

IPSEC\_CONNECTION\_READ

`ListCrossConnects`

CROSS\_CONNECT\_READ

`GetCrossConnect`

CROSS\_CONNECT\_READ

`UpdateCrossConnect`

CROSS\_CONNECT\_UPDATE

`CreateCrossConnect`

CROSS\_CONNECT\_CREATE if not creating cross-connect in a cross-connect group.

If creating the cross-connect in a cross-connect group, also need CROSS\_CONNECT\_CREATE and CROSS\_CONNECT\_ATTACH

`DeleteCrossConnect`

CROSS\_CONNECT\_DELETE if cross-connect is not in a cross-connect group.

If the cross-connect is in a cross-connect group, also need CROSS\_CONNECT\_DELETE and CROSS\_CONNECT\_DETACH

`ChangeCrossConnectCompartment`

CROSS\_CONNECT\_RESOURCE\_MOVE

`ListCrossConnectGroups`

CROSS\_CONNECT\_GROUP\_READ

`GetCrossConnectGroup`

CROSS\_CONNECT\_GROUP\_READ

`UpdateCrossConnectGroup`

CROSS\_CONNECT\_GROUP\_UPDATE

`CreateCrossConnectGroup`

CROSS\_CONNECT\_GROUP\_CREATE

`DeleteCrossConnectGroup`

CROSS\_CONNECT\_GROUP\_DELETE

`ChangeCrossConnectGroupCompartment`

CROSS\_CONNECT\_GROUP\_RESOURCE\_MOVE

`ListDhcpOptions`

DHCP\_READ

`GetDhcpOptions`

DHCP\_READ

`UpdateDhcpOptions`

DHCP\_UPDATE

`CreateDhcpOptions`

DHCP\_CREATE and VCN\_ATTACH

`DeleteDhcpOptions`

DHCP\_DELETE and VCN\_DETACH

`ChangeDhcpOptionsCompartment`

DHCP\_MOVE

`ListDrgs`

DRG\_READ

`GetDrg`

DRG\_READ

`UpdateDrg`

DRG\_UPDATE

`CreateDrg`

DRG\_CREATE

`DeleteDrg`

DRG\_DELETE

`ChangeDrgCompartment`

DRG\_MOVE

`ListDrgAttachments`

DRG\_ATTACHMENT\_READ

`GetDrgAttachment`

DRG\_ATTACHMENT\_READ

`UpdateDrgAttachment`

DRG\_ATTACHMENT\_UPDATE

ROUTE\_TABLE\_ATTACH is necessary to associate a route table with the DRG attachment during the update.

`CreateDrgAttachment`

DRG\_ATTACH and VCN\_ATTACH

ROUTE\_TABLE\_ATTACH is necessary to associate a route table with the DRG attachment during creation.

`DeleteDrgAttachment`

DRG\_DETACH or VCN\_DETACH

`GetAllDrgAttachments`

DRG\_READ

`UpgradeDrg`

DRG\_UPDATE

`ListAttachmentsToDrg`

DRG\_READ

`ListDrgAttachments`

DRG\_ATTACHMENT\_READ

`CreateDrgRouteTable`

DRG\_ROUTE\_TABLE\_CREATE

`DeleteDrgRouteTable`

DRG\_ROUTE\_TABLE\_DELETE

`GetDrgRouteTable`

DRG\_ROUTE\_TABLE\_READ

`ListDrgRouteTables`

DRG\_ROUTE\_TABLE\_READ

`UpdateDrgRouteTable`

DRG\_ROUTE\_TABLE\_UPDATE

`UpdateDrgRouteRules`

DRG\_ROUTE\_RULE\_UPDATE

`RemoveDrgRouteRules`

DRG\_ROUTE\_RULE\_UPDATE

`AddDrgRouteRules`

DRG\_ROUTE\_RULE\_UPDATE

`ListDrgRouteRules`

DRG\_ROUTE\_RULE\_READ

`GetDrgRouteDistribution`

DRG\_ROUTE\_DISTRIBUTION\_READ

`ListDrgRouteDistributions`

DRG\_ROUTE\_DISTRIBUTION\_READ

`CreateDrgRouteDistribution`

DRG\_ROUTE\_DISTRIBUTION\_CREATE

`DeleteDrgRouteDistribution`

DRG\_ROUTE\_DISTRIBUTION\_DELETE

`UpdateDrgRouteDistribution`

DRG\_ROUTE\_DISTRIBUTION\_UPDATE

`UpdateDrgRouteDistributionStatements`

DRG\_ROUTE\_DISTRIBUTION\_STATEMENT\_UPDATE

`RemoveDrgRouteDistributionStatements`

DRG\_ROUTE\_DISTRIBUTION\_STATEMENT\_UPDATE

`AddDrgRouteDistributionStatements`

DRG\_ROUTE\_DISTRIBUTION\_STATEMENT\_UPDATE

`ListDrgRouteDistributionStatements`

DRG\_ROUTE\_DISTRIBUTION\_STATEMENT\_READ

`RemoveExportDrgRouteDistribution`

DRG\_ROUTE\_DISTRIBUTION\_ASSIGN

`RemoveImportDrgRouteDistribution`

DRG\_ROUTE\_DISTRIBUTION\_ASSIGN

`CreateInstanceConsoleConnection`

INSTANCE\_CONSOLE\_CONNECTION\_CREATE and INSTANCE\_READ

`DeleteInstanceConsoleConnection`

INSTANCE\_CONSOLE\_CONNECTION\_DELETE

`GetInstanceConsoleConnection`

INSTANCE\_CONSOLE\_CONNECTION\_READ and INSTANCE\_READ

`UpdateInstanceConsoleConnection`

INSTANCE\_CONSOLE\_CONNECTION\_CREATE and INSTANCE\_CONSOLE\_CONNECTION\_DELETE

`ListInstanceConsoleConnections`

INSTANCE\_CONSOLE\_CONNECTION\_INSPECT and INSTANCE\_INSPECT and INSTANCE\_READ

`ListImages`

INSTANCE\_IMAGE\_INSPECT

`GetImage`

INSTANCE\_IMAGE\_INSPECT

`UpdateImage`

INSTANCE\_IMAGE\_UPDATE

`CreateImage`

INSTANCE\_IMAGE\_CREATE and INSTANCE\_CREATE\_IMAGE

The first permission is related to the `instance-image`; the second is related to the `instance`.

`ChangeImageCompartment`

INSTANCE\_IMAGE\_MOVE

`DeleteImage`

INSTANCE\_IMAGE\_DELETE

`GetComputeGlobalImageCapabilitySchema`

COMPUTE\_GLOBAL\_IMAGE\_CAPABILITY\_SCHEMA\_READ

`GetComputeGlobalImageCapabilitySchemaVersion`

COMPUTE\_GLOBAL\_IMAGE\_CAPABILITY\_SCHEMA\_READ

`ListComputeGlobalImageCapabilitySchemas`

COMPUTE\_GLOBAL\_IMAGE\_CAPABILITY\_SCHEMA\_INSPECT

`ListComputeGlobalImageCapabilitySchemaVersions`

COMPUTE\_GLOBAL\_IMAGE\_CAPABILITY\_SCHEMA\_INSPECT

`CreateComputeImageCapabilitySchema`

COMPUTE\_IMAGE\_CAPABILITY\_SCHEMA\_CREATE

`ListComputeImageCapabilitySchemas`

COMPUTE\_IMAGE\_CAPABILITY\_SCHEMA\_INSPECT

`GetComputeImageCapabilitySchema`

COMPUTE\_IMAGE\_CAPABILITY\_SCHEMA\_READ

`UpdateComputeImageCapabilitySchema`

COMPUTE\_IMAGE\_CAPABILITY\_SCHEMA\_UPDATE

`ChangeComputeImageCapabilitySchemaCompartment`

COMPUTE\_IMAGE\_CAPABILITY\_SCHEMA\_MOVE

`DeleteComputeImageCapabilitySchema`

COMPUTE\_IMAGE\_CAPABILITY\_SCHEMA\_DELETE

`LaunchInstance`

INSTANCE\_CREATE and INSTANCE\_IMAGE\_READ and VNIC\_CREATE and VNIC\_ATTACH and SUBNET\_ATTACH

If putting the instance in a network security group during instance creation, also need NETWORK\_SECURITY\_GROUP\_UPDATE\_MEMBERS and VNIC\_ASSOCIATE\_NETWORK\_SECURITY\_GROUP

If creating an instance in a compute cluster, also need COMPUTE\_CLUSTER\_LAUNCH\_INSTANCE

`ListInstances`

INSTANCE\_READ

If listing instances in a compute cluster, also need COMPUTE\_CLUSTER\_READ

`ListInstanceDevices`

INSTANCE\_READ

`GetInstance`

INSTANCE\_READ

`GetInstanceMaintenanceReboot`

INSTANCE\_READ

`UpdateInstance`

INSTANCE\_UPDATE

`InstanceAction`

INSTANCE\_POWER\_ACTIONS

`ChangeInstanceCompartment`

INSTANCE\_MOVE

`TerminateInstance`

INSTANCE\_DELETE and VNIC\_DELETE and SUBNET\_DETACH

If volumes are attached, also need VOLUME\_ATTACHMENT\_DELETE and VOLUME\_WRITE and INSTANCE\_DETACH\_VOLUME

`ListInstanceConfigurations`

INSTANCE\_CONFIGURATION\_INSPECT

`GetInstanceConfiguration`

INSTANCE\_CONFIGURATION\_READ

`LaunchInstanceConfiguration`

INSTANCE\_CONFIGURATION\_LAUNCH

`UpdateInstanceConfiguration`

INSTANCE\_CONFIGURATION\_UPDATE

`CreateInstanceConfiguration`

INSTANCE\_CONFIGURATION\_CREATE (if using the `CreateInstanceConfigurationDetails` subtype)

INSTANCE\_READ and VNIC\_READ and VNIC\_ATTACHMENT\_READ and VOLUME\_INSPECT and VOLUME\_ATTACHMENT\_INSPECT (if using the `CreateInstanceConfigurationFromInstanceDetails` subtype)

`ChangeInstanceConfigurationCompartment`

INSTANCE\_CONFIGURATION\_MOVE

`DeleteInstanceConfiguration`

INSTANCE\_CONFIGURATION\_DELETE

`ListInstanceMaintenanceEvent`

INSTANCE\_MAINTENANCE\_EVENT\_INSPECT

`GetInstanceMaintenanceEvent`

INSTANCE\_MAINTENANCE\_EVENT\_READ

`UpdateInstanceMaintenanceEvent`

INSTANCE\_MAINTENANCE\_EVENT\_UPDATE

`CreateInstancePool`

INSTANCE\_POOL\_CREATE and INSTANCE\_CREATE and IMAGE\_READ and VNIC\_CREATE and SUBNET\_ATTACH

`ListInstancePools`

INSTANCE\_POOL\_INSPECT

`ListInstancePoolInstances`

INSTANCE\_POOL\_READ

`GetInstancePool`

INSTANCE\_POOL\_READ

`UpdateInstancePool`

INSTANCE\_POOL\_UPDATE

`AttachInstancePoolInstance`

INSTANCE\_POOL\_INSTANCE\_ATTACH

`DetachInstancePoolInstance`

INSTANCE\_POOL\_INSTANCE\_DETACH

`StartInstancePool`

INSTANCE\_POOL\_POWER\_ACTIONS

`StopInstancePool`

INSTANCE\_POOL\_POWER\_ACTIONS

`ResetInstancePool`

INSTANCE\_POOL\_POWER\_ACTIONS

`SoftresetInstancePool`

INSTANCE\_POOL\_POWER\_ACTIONS

`ChangeInstancePoolCompartment`

INSTANCE\_POOL\_MOVE

`TerminateInstancePool`

INSTANCE\_POOL\_DELETE and INSTANCE\_DELETE and VNIC\_DELETE and SUBNET\_DETACH and VOLUME\_ATTACHMENT\_DELETE and VOLUME\_WRITE

`ListInternetGateways`

INTERNET\_GATEWAY\_READ

`GetInternetGateway`

INTERNET\_GATEWAY\_READ

`UpdateInternetGateway`

INTERNET\_GATEWAY\_UPDATE

`CreateInternetGateway`

INTERNET\_GATEWAY\_CREATE and VCN\_ATTACH

`DeleteInternetGateway`

INTERNET\_GATEWAY\_DELETE and VCN\_DETACH

`ChangeInternetGatewayCompartment`

INTERNET\_GATEWAY\_MOVE

`ListIPSecConnections`

IPSEC\_CONNECTION\_READ

`GetIPSecConnection`

IPSEC\_CONNECTION\_READ

`UpdateIpSecConnection`

IPSEC\_CONNECTION\_UPDATE

`CreateIPSecConnection`

DRG\_ATTACH and CPE\_ATTACH and IPSEC\_CONNECTION\_CREATE

Required to create IPSec over FastConnect: DRG\_ROUTE\_TABLE\_ATTACH, DRG\_ROUTE\_TABLE\_CREATE DRG\_ROUTE\_TABLE\_UPDATE, DRG\_ROUTE\_DISTRIBUTION\_CREATE, DRG\_ROUTE\_DISTRIBUTION\_UPDATE, DRG\_ROUTE\_DISTRIBUTION\_ASSIGN, DRG\_ROUTE\_DISTRIBUTION\_STATEMENT\_UPDATE

`DeleteIPSecConnection`

DRG\_DETACH and CPE\_DETACH and IPSEC\_CONNECTION\_DELETE

Required to create IPSec over FastConnect: DRG\_ROUTE\_TABLE\_DELETE DRG\_ROUTE\_TABLE\_UPDATE, DRG\_ROUTE\_DISTRIBUTION\_DELETE, DRG\_ROUTE\_DISTRIBUTION\_UPDATE, DRG\_ROUTE\_DISTRIBUTION\_STATEMENT\_UPDATE

`GetIPSecConnectionDeviceConfig`

IPSEC\_CONNECTION\_DEVICE\_CONFIG\_READ

`GetIPSecConnectionDeviceStatus`

IPSEC\_CONNECTION\_READ

`ListIPSecConnectionTunnels`

IPSEC\_CONNECTION\_READ

`GetIPSecConnectionTunnel`

IPSEC\_CONNECTION\_READ

`UpdateIPSecConnectionTunnel`

IPSEC\_CONNECTION\_UPDATE

`GetIPSecConnectionTunnelSharedSecret`

IPSEC\_CONNECTION\_DEVICE\_CONFIG\_READ

`UpdateIPSecConnectionTunnelSharedSecret`

IPSEC\_CONNECTION\_DEVICE\_CONFIG\_UPDATE

`ListIpv6s`

IPV6\_READ and SUBNET\_READ (if listing by subnet) and VNIC\_READ (if listing by VNIC)

`GetIpv6`

IPV6\_READ

`UpdateIpv6`

IPV6\_UPDATE and

VNIC\_UNASSIGN and VNIC\_ASSIGN (if moving IPv6 to a different VNIC)

`CreateIpv6`

IPV6\_CREATE and SUBNET\_ATTACH and VNIC\_ASSIGN

`DeleteIpv6`

IPV6\_DELETE and SUBNET\_DETACH and VNIC\_UNASSIGN

`ListLocalPeeringGateways`

LOCAL\_PEERING\_GATEWAY\_READ

`GetLocalPeeringGateway`

LOCAL\_PEERING\_GATEWAY\_READ

`UpdateLocalPeeringGateway`

LOCAL\_PEERING\_GATEWAY\_UPDATE

ROUTE\_TABLE\_ATTACH is necessary to associate a route table with the LPG during the update.

`CreateLocalPeeringGateway`

LOCAL\_PEERING\_GATEWAY\_CREATE and VCN\_ATTACH

ROUTE\_TABLE\_ATTACH is necessary to associate a route table with the LPG during creation.

`DeleteLocalPeeringGateway`

LOCAL\_PEERING\_GATEWAY\_DELETE and VCN\_DETACH

`ConnectLocalPeeringGateway`

LOCAL\_PEERING\_GATEWAY\_CONNECT\_FROM and

LOCAL\_PEERING\_GATEWAY\_CONNECT\_TO

`ChangeLocalPeeringGatewayCompartment`

LOCAL\_PEERING\_GATEWAY\_MOVE

`ListNatGateways`

NAT\_GATEWAY\_READ

`GetNatGateway`

NAT\_GATEWAY\_READ

`UpdateNatGateway`

NAT\_GATEWAY\_UPDATE

`CreateNatGateway`

NAT\_GATEWAY\_CREATE and VCN\_READ and VCN\_ATTACH

`DeleteNatGateway`

NAT\_GATEWAY\_DELETE and VCN\_READ and VCN\_DETACH

`ChangeNatGatewayCompartment`

NAT\_GATEWAY\_MOVE

`ListNetworkSecurityGroups`

NETWORK\_SECURITY\_GROUP\_READ

`GetNetworkSecurityGroup`

NETWORK\_SECURITY\_GROUP\_READ

`UpdateNetworkSecurityGroup`

NETWORK\_SECURITY\_GROUP\_UPDATE

`CreateNetworkSecurityGroup`

NETWORK\_SECURITY\_GROUP\_CREATE and VCN\_ATTACH

`DeleteNetworkSecurityGroup`

NETWORK\_SECURITY\_GROUP\_DELETE and VCN\_DETACH

`ChangeNetworkSecurityGroupCompartment`

NETWORK\_SECURITY\_GROUP\_MOVE

`ListNetworkSecurityGroupSecurityRules`

NETWORK\_SECURITY\_GROUP\_LIST\_SECURITY\_RULES

`UpdateNetworkSecurityGroupSecurityRules`

NETWORK\_SECURITY\_GROUP\_UPDATE\_SECURITY\_RULES and

NETWORK\_SECURITY\_GROUP\_INSPECT if writing a rule that specifies a network security group as the source (for ingress rules) or destination (for egress rules)

`AddNetworkSecurityGroupSecurityRules`

NETWORK\_SECURITY\_GROUP\_UPDATE\_SECURITY\_RULES and

NETWORK\_SECURITY\_GROUP\_INSPECT if writing a rule that specifies a network security group as the source (for ingress rules) or destination (for egress rules)

`RemoveNetworkSecurityGroupSecurityRules`

NETWORK\_SECURITY\_GROUP\_UPDATE\_SECURITY\_RULES

`ListPrivateIps`

PRIVATE\_IP\_READ

`GetPrivateIp`

PRIVATE\_IP\_READ

`UpdatePrivateIp`

PRIVATE\_IP\_UPDATE and VNIC\_ASSIGN and VNIC\_UNASSIGN

`CreatePrivateIp`

PRIVATE\_IP\_CREATE and PRIVATE\_IP\_ASSIGN and VNIC\_ASSIGN and SUBNET\_ATTACH

`DeletePrivateIp`

PRIVATE\_IP\_DELETE and PRIVATE\_IP\_UNASSIGN and VNIC\_UNASSIGN and SUBNET\_DETACH

`ListRemotePeeringConnections`

REMOTE\_PEERING\_CONNECTION\_READ

`GetRemotePeeringConnection`

REMOTE\_PEERING\_CONNECTION\_READ

`UpdateRemotePeeringConnection`

REMOTE\_PEERING\_CONNECTION\_UPDATE

`CreateRemotePeeringConnection`

REMOTE\_PEERING\_CONNECTION\_CREATE and DRG\_ATTACH

`DeleteRemotePeeringConnection`

REMOTE\_PEERING\_CONNECTION\_DELETE and DRG\_DETACH

`ChangeRemotePeeringConnectionCompartment`

REMOTE\_PEERING\_CONNECTION\_RESOURCE\_MOVE

`ConnectRemotePeeringConnections`

REMOTE\_PEERING\_CONNECTION\_CONNECT\_FROM and

REMOTE\_PEERING\_CONNECTION\_CONNECT\_TO

`ListPublicIps`

For ephemeral public IPs: PRIVATE\_IP\_READ

For reserved public IPs: PUBLIC\_IP\_READ

`GetPublicIp`

For ephemeral public IPs: PRIVATE\_IP\_READ

For reserved public IPs: PUBLIC\_IP\_READ

`GetPublicIpByPrivateIpId`

For ephemeral public IPs: PRIVATE\_IP\_READ

For reserved public IPs: PUBLIC\_IP\_READ

`GetPublicIpByIpAddress`

For ephemeral public IPs: PRIVATE\_IP\_READ

For reserved public IPs: PUBLIC\_IP\_READ

`UpdatePublicIP`

For ephemeral public IPs: PRIVATE\_IP\_UPDATE

For reserved public IPs: PUBLIC\_IP\_UPDATE and PRIVATE\_IP\_ASSIGN\_PUBLIC\_IP and PUBLIC\_IP\_ASSIGN\_PRIVATE\_IP and PRIVATE\_IP\_UNASSIGN\_PUBLIC\_IP and PUBLIC\_IP\_UNASSIGN\_PRIVATE\_IP

`CreatePublicIp`

For ephemeral public IPs: PRIVATE\_IP\_ASSIGN\_PUBLIC\_IP

For reserved public IPs: PUBLIC\_IP\_CREATE and PUBLIC\_IP\_ASSIGN\_PRIVATE\_IP and PRIVATE\_IP\_ASSIGN\_PUBLIC\_IP

`DeletePublicIp`

For ephemeral public IPs: PRIVATE\_IP\_UNASSIGN\_PUBLIC\_IP

For reserved public IPs: PUBLIC\_IP\_DELETE and PUBLIC\_IP\_UNASSIGN\_PRIVATE\_IP and PRIVATE\_IP\_UNASSIGN\_PUBLIC\_IP

`ChangePublicIpCompartment`

PUBLIC\_IP\_MOVE

Note: This operation applies only to reserved public IPs.

`ListRouteTables`

ROUTE\_TABLE\_READ

`GetRouteTable`

ROUTE\_TABLE\_READ

`UpdateRouteTable`

ROUTE\_TABLE\_UPDATE and

INTERNET\_GATEWAY\_ATTACH (if creating a route rule that uses an internet gateway as a target) and

INTERNET\_GATEWAY\_DETACH (if deleting a route rule that uses an internet gateway as a target) and

DRG\_ATTACH (if creating a route rule that uses a DRG as a target) and

DRG\_DETACH (if deleting a route rule that uses a DRG as a target) and

PRIVATE\_IP\_ROUTE\_TABLE\_ATTACH (if creating a route rule that uses a private IP as a target) and

PRIVATE\_IP\_ROUTE\_TABLE\_DETACH (if deleting a route rule that uses a private IP as a target) and

LOCAL\_PEERING\_GATEWAY\_ATTACH (if creating a route rule that uses an LPG as a target) and

LOCAL\_PEERING\_GATEWAY\_DETACH (if deleting a route rule that uses an LPG as a target) and

NAT\_GATEWAY\_ATTACH (if creating a route rule that uses a NAT gateway as a target) and

NAT\_GATEWAY\_DETACH (if deleting a route rule that uses a NAT gateway as a target) and

SERVICE\_GATEWAY\_ATTACH (if creating a route rule that uses a service gateway as a target) and

SERVICE\_GATEWAY\_DETACH (if deleting a route rule that uses a service gateway as a target)

`CreateRouteTable`

ROUTE\_TABLE\_CREATE and VCN\_ATTACH and

INTERNET\_GATEWAY\_ATTACH (if creating a route rule that uses an internet gateway as a target) and

DRG\_ATTACH (if creating a route rule that uses a DRG as a target) and

PRIVATE\_IP\_ROUTE\_TABLE\_ATTACH (if creating a route rule that uses a private IP as a target) and

LOCAL\_PEERING\_GATEWAY\_ATTACH (if creating a route rule that uses an LPG as a target) and

NAT\_GATEWAY\_ATTACH (if creating a route rule that uses a NAT gateway as a target) and

SERVICE\_GATEWAY\_ATTACH (if creating a route rule that uses a service gateway as a target)

`DeleteRouteTable`

ROUTE\_TABLE\_DELETE and VCN\_DETACH and

INTERNET\_GATEWAY\_DETACH (if deleting a route rule that uses an internet gateway as a target) and

DRG\_DETACH (if deleting a route rule that uses a DRG as a target) and

PRIVATE\_IP\_ROUTE\_TABLE\_DETACH (if deleting a route rule that uses a private IP as a target) and

LOCAL\_PEERING\_GATEWAY\_DETACH (if deleting a route rule that uses an LPG as a target) and

NAT\_GATEWAY\_DETACH (if deleting a route rule that uses a NAT gateway as a target) and

SERVICE\_GATEWAY\_DETACH (if deleting a route rule that uses a service gateway as a target)

`ChangeRouteTableCompartment`

ROUTE\_TABLE\_MOVE

`ListSecurityLists`

SECURITY\_LIST\_READ

`GetSecurityList`

SECURITY\_LIST\_READ

`UpdateSecurityList`

SECURITY\_LIST\_UPDATE

`ChangeSecurityListCompartment`

SECURITY\_LIST\_MOVE

`CreateSecurityList`

SECURITY\_LIST\_CREATE and VCN\_ATTACH

`DeleteSecurityList`

SECURITY\_LIST\_DELETE and VCN\_DETACH

`ListServiceGateways`

SERVICE\_GATEWAY\_READ

`GetServiceGateway`

SERVICE\_GATEWAY\_READ

`UpdateServiceGateway`

SERVICE\_GATEWAY\_UPDATE

ROUTE\_TABLE\_ATTACH is necessary to associate a route table with the service gateway during the update.

`ChangeServiceGatewayCompartment`

SERVICE\_GATEWAY\_MOVE

`CreateServiceGateway`

SERVICE\_GATEWAY\_CREATE and VCN\_READ and VCN\_ATTACH

ROUTE\_TABLE\_ATTACH is necessary to associate a route table with the service gateway during creation.

`DeleteServiceGateway`

SERVICE\_GATEWAY\_DELETE and VCN\_READ and VCN\_DETACH

`AttachServiceId`

SERVICE\_GATEWAY\_ADD\_SERVICE

`DetachServiceId`

SERVICE\_GATEWAY\_DELETE\_SERVICE

`ListShapes`

INSTANCE\_INSPECT

`ListSubnets`

SUBNET\_READ

`GetSubnet`

SUBNET\_READ

`UpdateSubnet`

SUBNET\_UPDATE

If changing which route table is associated with the subnet, also need ROUTE\_TABLE\_ATTACH and ROUTE\_TABLE\_DETACH

If changing which security lists are associated with the subnet, also need SECURITY\_LIST\_ATTACH and SECURITY\_LIST\_DETACH

If changing which set of DHCP options are associated with the subnet, also need DHCP\_ATTACH and DHCP\_DETACH

`CreateSubnet`

SUBNET\_CREATE and VCN\_ATTACH and ROUTE\_TABLE\_ATTACH and SECURITY\_LIST\_ATTACH and DHCP\_ATTACH

`DeleteSubnet`

SUBNET\_DELETE and VCN\_DETACH and ROUTE\_TABLE\_DETACH and SECURITY\_LIST\_DETACH and DHCP\_DETACH

`ChangeSubnetCompartment`

SUBNET\_MOVE

`ListVcns`

VCN\_READ

`GetVcn`

VCN\_READ

`UpdateVcn`

VCN\_UPDATE

`CreateVcn`

VCN\_CREATE

`DeleteVcn`

VCN\_DELETE

`AddVcnCidr`

VCN\_UPDATE

`ModifyVcnCidr`

VCN\_UPDATE

`RemoveVcnCidr`

VCN\_UPDATE

`ChangeVcnCompartment`

VCN\_MOVE

`ListVirtualCircuits`

VIRTUAL\_CIRCUIT\_READ

`GetVirtualCircuit`

VIRTUAL\_CIRCUIT\_READ

`UpdateVirtualCircuit`

VIRTUAL\_CIRCUIT\_UPDATE and DRG\_ATTACH and DRG\_DETACH

If updating which cross-connect or cross-connect group the virtual circuit is using, also need CROSS\_CONNECT\_DETACH and CROSS\_CONNECT\_ATTACH

`CreateVirtualCircuit`

VIRTUAL\_CIRCUIT\_CREATE and DRG\_ATTACH

If creating the virtual circuit with a mapping to a specific cross-connect or cross-connect group, also need CROSS\_CONNECT\_ATTACH

`DeleteVirtualCircuit`

VIRTUAL\_CIRCUIT\_DELETE and DRG\_DETACH

If deleting a virtual circuit that's currently using a cross-connect or cross-connect group, also need CROSS\_CONNECT\_DETACH

`changeVirtualCircuitCompartment`

VIRTUAL\_CIRCUIT\_RESOURCE\_MOVE

`ListVlans`

VLAN\_READ

`GetVlan`

VLAN\_READ

`CreateVlan`

VLAN\_CREATE and VCN\_ATTACH and ROUTE\_TABLE\_ATTACH and SECURITY\_LIST\_ATTACH and VLAN\_ASSOCIATE\_NETWORK\_SECURITY\_GROUP

`UpdateVlan`

VLAN\_UPDATE

`DeleteVlan`

VLAN\_DELETE and VCN\_DETACH and ROUTE\_TABLE\_DETACH and SECURITY\_LIST\_DETACH and VLAN\_DISASSOCIATE\_NETWORK\_SECURITY\_GROUP

`ChangeVlanCompartment`

VLAN\_MOVE

`GetVnic`

VNIC\_READ

`AttachVnic`

INSTANCE\_ATTACH\_SECONDARY\_VNIC and VNIC\_ATTACH and VNIC\_CREATE and SUBNET\_ATTACH

If putting the secondary VNIC in a network security group during VNIC creation, also need NETWORK\_SECURITY\_GROUP\_UPDATE\_MEMBERS and VNIC\_ASSOCIATE\_NETWORK\_SECURITY\_GROUP

`DetachVnic`

INSTANCE\_DETACH\_SECONDARY\_VNIC and VNIC\_DETACH and VNIC\_DELETE and SUBNET\_DETACH

`UpdateVnic`

VNIC\_UPDATE

If adding or removing the VNIC from a network security group, also need NETWORK\_SECURITY\_GROUP\_UPDATE\_MEMBERS and VNIC\_ASSOCIATE\_NETWORK\_SECURITY\_GROUP

`ListVnicAttachments`

VNIC\_ATTACHMENT\_READ and INSTANCE\_INSPECT

`GetVnicAttachment`

VNIC\_ATTACHMENT\_READ

`ChangeVtapCompartment`

VTAP\_MOVE

`CreateVtap`

VTAP\_CREATE and CAPTURE\_FILTER\_ATTACH (in capture filter compartment) and VNIC\_ATTACH (both source and target in source & target compartment) || SUBNET\_ATTACH(when subnet as source) and VCN\_ATTACH (in VCN compartment)

`DeleteVtap`

VTAP\_DELETE and CAPTURE\_FILTER\_DETACH and NLB\_VTAP\_TARGET\_DETACH (when NLB as target) and VNIC\_DETACH (both source and target) or SUBNET\_DETACH (when subnet as source) or LB\_VTAP\_DISABLE (when load balancer as source) or DB\_SYSTEM\_VTAP\_DISABLE (when DB as source) or EXADATA\_VM\_CLUSTER\_VTAP\_DISABLE (when Exadata cluster as source) or ADW\_VTAP\_DISABLE (when ADW as source) and VCN\_DETACH

`GetVtap`

VTAP\_READ

`ListVtaps`

VTAP\_LIST

`UpdateVtap`

VTAP\_UPDATE and CAPTURE\_FILTER\_ATTACH (new) and NLB\_VTAP\_TARGET\_ATTACH (when NLB as target) and VNIC\_ATTACH (both new source and target) or SUBNET\_ATTACH (when subnet as source) or LB\_VTAP\_ENABLE (when load balancer as source) or DB\_SYSTEM\_VTAP\_ENABLE (when DB system as source) or EXADATA\_VM\_CLUSTER\_VTAP\_ENABLE (when Exadata cluster as source) or ADW\_VTAP\_ENABLE (when ADW as source) and NLB\_VTAP\_TARGET\_DETACH (when NLB as target) and CAPTURE\_FILTER\_DETACH (old) and VNIC\_DETACH (both old source and target) or SUBNET\_DETACH (when subnet as source) or LB\_VTAP\_DISABLE (when load balancer as source) or DB\_SYSTEM\_VTAP\_DISABLE (when DB system as source) or EXADATA\_VM\_CLUSTER\_VTAP\_DISABLE (when Exadata cluster as source) or ADW\_VTAP\_DISABLE (when ADW as source)

`ChangeCaptureFilterCompartment`

CAPTURE\_FILTER\_MOVE

`CreateCaptureFilter`

CAPTURE\_FILTER\_CREATE and VCN\_ATTACH

`DeleteCaptureFilter`

CAPTURE\_FILTER\_DELETE and VCN\_DETACH

`GetCaptureFilter`

CAPTURE\_FILTER\_READ

`ListCaptureFilters`

CAPTURE\_FILTER\_LIST

`UpdateCaptureFilter`

CAPTURE\_FILTER\_UPDATE

`GetVolume`

VOLUME\_INSPECT

`ListVolumes`

VOLUME\_INSPECT

`UpdateVolume`

VOLUME\_UPDATE

`CreateVolume`

VOLUME\_CREATE (and VOLUME\_BACKUP\_READ if creating volume from a backup)

`DeleteVolume`

VOLUME\_DELETE

`ChangeVolumeCompartment`

VOLUME\_MOVE

`ListVolumeAttachments`

VOLUME\_ATTACHMENT\_INSPECT and VOLUME\_INSPECT and INSTANCE\_INSPECT

`GetVolumeAttachment`

VOLUME\_ATTACHMENT\_INSPECT and INSTANCE\_INSPECT

**Note:** To also get the CHAP secret for the volume, then VOLUME\_ATTACHMENT\_READ is required instead of VOLUME\_ATTACHMENT\_INSPECT

`AttachVolume`

VOLUME\_ATTACHMENT\_CREATE and VOLUME\_WRITE and INSTANCE\_ATTACH\_VOLUME

`DetachVolume`

VOLUME\_ATTACHMENT\_DELETE and VOLUME\_WRITE and INSTANCE\_DETACH\_VOLUME

`ListVolumeBackups`

VOLUME\_BACKUP\_INSPECT and VOLUME\_INSPECT

`GetVolumeBackup`

VOLUME\_BACKUP\_INSPECT and VOLUME\_INSPECT

`UpdateVolumeBackup`

VOLUME\_BACKUP\_UPDATE and VOLUME\_INSPECT

`CreateVolumeBackup`

VOLUME\_BACKUP\_CREATE and VOLUME\_WRITE

`DeleteVolumeBackup`

VOLUME\_BACKUP\_DELETE and VOLUME\_INSPECT

`ChangeVolumeBackupCompartment`

VOLUME\_BACKUP\_MOVE

`GetBootVolume`

VOLUME\_INSPECT

`ListBootVolumes`

VOLUME\_INSPECT

`UpdateBootVolume`

VOLUME\_UPDATE

`DeleteBootVolume`

VOLUME\_DELETE

`ChangeBootVolumeCompartment`

BOOT\_VOLUME\_MOVE

`CreateBootVolumeBackup`

BOOT\_VOLUME\_BACKUP\_CREATE, VOLUME\_WRITE

`ListBootVolumeBackups`

BOOT\_VOLUME\_BACKUP\_INSPECT, VOLUME\_INSPECT

`GetBootVolumeBackup`

BOOT\_VOLUME\_BACKUP\_INSPECT, VOLUME\_INSPECT

`UpdateBootVolumeBackup`

BOOT\_VOLUME\_BACKUP\_UPDATE, VOLUME\_INSPECT

`DeleteBootVolumeBackup`

BOOT\_VOLUME\_BACKUP\_DELETE, VOLUME\_INSPECT

`ChangeBootVolumeBackupCompartment`

BOOT\_VOLUME\_BACKUP\_MOVE

`CreateVolumeGroup`

VOLUME\_GROUP\_CREATE, VOLUME\_INSPECT if creating the volume group from a list of volumes.

VOLUME\_GROUP\_CREATE, VOLUME\_GROUP\_INSPECT, VOLUME\_CREATE, VOLUME\_WRITE if cloning a volume group.

VOLUME\_GROUP\_CREATE, VOLUME\_GROUP\_BACKUP\_INSPECT, VOLUME\_BACKUP\_READ/BOOT\_VOLUME\_BACKUP\_READ, VOLUME\_CREATE, VOLUME\_WRITE if restoring from a volume group backup.

`DeleteVolumeGroup`

VOLUME\_GROUP\_DELETE

`GetVolumeGroup`

VOLUME\_GROUP\_INSPECT

`ListVolumeGroups`

VOLUME\_GROUP\_INSPECT

`UpdateVolumeGroup`

VOLUME\_GROUP\_UPDATE, VOLUME\_INSPECT

`ChangeVolumegGroupCompartment`

VOLUME\_GROUP\_MOVE, VOLUME\_MOVE/BOOT\_VOLUME\_MOVE

`CreateVolumeGroupBackup`

VOLUME\_GROUP\_BACKUP\_CREATE, VOLUME\_GROUP\_INSPECT, VOLUME\_WRITE, VOLUME\_BACKUP\_CREATE/BOOT\_VOLUME\_BACKUP\_CREATE

`DeleteVolumeGroupBackup`

VOLUME\_GROUP\_BACKUP\_DELETE, VOLUME\_BACKUP\_DELETE/BOOT\_VOLUME\_BACKUP\_DELETE

`GetVolumeGroupBackup`

VOLUME\_GROUP\_BACKUP\_INSPECT

`ListVolumeGroupBackups`

VOLUME\_GROUP\_BACKUP\_INSPECT

`UpdateVolumeGroupBackup`

VOLUME\_GROUP\_BACKUP\_UPDATE

`ChangeVolumegGroupBackupCompartment`

VOLUME\_GROUP\_BACKUP\_MOVE, VOLUME\_BACKUP\_MOVE/BOOT\_VOLUME\_BACKUP\_MOVE

`ListIpInventory`

IPAM\_READ

`GetVcnOverlap`

IPAM\_READ

`GetSubnetIpInventory`

IPAM\_READ

`GetSubnetCidrUtilization`

IPAM\_READ