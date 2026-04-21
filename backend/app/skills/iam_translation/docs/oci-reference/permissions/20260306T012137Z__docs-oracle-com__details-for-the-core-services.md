# Details for the Core Services

Source: https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference.htm
(Includes content from sub-pages: `corepolicyreference_topic-ResourceTypes.htm`, `corepolicyreference_topic-Details_for_Verb__ResourceType_Combinations.htm`, `corepolicyreference_topic-Permissions_Required_for_Each_API_Operation.htm`.)
Captured: 2026-03-06

This topic covers the permissions and API operations for Core Services (Networking, Compute, Block Volume).

## Resource-Types

### Networking

**Aggregate:** `virtual-network-family`, `drgs` (covers `drg-object`, `drg-route-table`, `drg-route-distribution`, `drg-attachment`)

**Individual:** `vcns`, `subnets`, `route-tables`, `network-security-groups`, `security-lists`, `dhcp-options`, `private-ips`, `public-ips`, `ipv6s`, `internet-gateways`, `nat-gateways`, `service-gateways`, `local-peering-gateways` (includes `local-peering-from`, `local-peering-to`), `remote-peering-connections` (includes `remote-peering-from`, `remote-peering-to`), `drg-object`, `drg-attachments`, `drg-route-tables`, `drg-route-distributions`, `cpes`, `ipsec-connections`, `cross-connects`, `cross-connect-groups`, `virtual-circuits`, `vnics`, `vtaps`, `vnic-attachments`, `vlans`, `byoiprange`, `publicippool`, `ipam`.

A policy that uses `<verb> virtual-network-family` is equivalent to writing a separate `<verb> <individual resource-type>` statement for each of these.

### Compute

**`instance-family`** covers: `app-catalog-listing`, `console-histories`, `instances`, `instance-console-connection`, `instance-images`, `volume-attachments` (only the permissions required for attaching volumes to instances).

**`compute-management-family`** covers: `instance-configurations`, `instance-pools`, `cluster-networks`.

**`instance-agent-family`** covers: `instance-agent-plugins`.

**`instance-agent-command-family`** covers: `instance-agent-commands`.

**Additional individual Compute resource-types** (not in any family): `auto-scaling-configurations`, `compute-bare-metal-hosts`, `compute-capacity-reports`, `compute-capacity-reservations`, `compute-clusters`, `compute-global-image-capability-schema`, `compute-gpu-memory-clusters`, `compute-gpu-memory-fabrics`, `compute-host-groups`, `compute-image-capability-schema`, `dedicated-vm-hosts`, `instance-agent-commands`, `work-requests`.

### Block Volume

**Aggregate:** `volume-family`

**Individual:** `volumes`, `volume-attachments`, `volume-backups`, `boot-volume-backups`, `backup-policies`, `backup-policy-assignments`, `volume-groups`, `volume-group-backups`.

## Details for Verb + Resource-Type Combinations

Tables below show the permissions and API operations covered by each verb. Access is cumulative: `inspect` → `read` → `use` → `manage`. A `+` indicates incremental access vs. the cell above; "no extra" indicates no incremental access.

### For `virtual-network-family` Resource Types

#### vcns

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VCN_READ | `ListVcns`, `GetVcn` | `CreateNatGateway`, `DeleteNatGateway` (both also need `manage nat-gateways` and `manage vcns`). **Note:** Totally covered with just `manage virtual-network-family`. |
| read | no extra | no extra | no extra |
| use | no extra | no extra | no extra |
| manage | USE + VCN_ATTACH, VCN_DETACH, VCN_UPDATE, VCN_CREATE, VCN_DELETE, VCN_MOVE | USE + `CreateVcn`, `UpdateVcn`, `DeleteVcn`, `AddVcnCidr`, `ModifyVcnCidr`, `RemoveVcnCidr`, `ChangeVcnCompartment`, `AddIpv6VcnCidr`, `RemoveIpv6VcnCidr` | USE + `CreateSubnet`, `DeleteSubnet` (both also need `manage route-tables`, `manage security-lists`, `manage dhcp-options`); `CreateInternetGateway`, `DeleteInternetGateway` (also need `manage internet-gateways`); `CreateLocalPeeringGateway` (also needs `manage local-peering-gateways`, plus `manage route-tables` if associating a route table on create); `DeleteLocalPeeringGateway` (also needs `manage local-peering-gateways`); `CreateNatGateway`, `DeleteNatGateway` (also need `manage nat-gateways`); `CreateNetworkSecurityGroup`, `DeleteNetworkSecurityGroup` (also need `manage network-security-groups`); `CreateRouteTable`, `DeleteRouteTable` (also need `manage route-tables`, `manage internet-gateways`, `manage drgs`, `manage private-ips`, `manage local-peering-gateways`, `use nat-gateways`, `use service-gateways`); `CreateServiceGateway`, `DeleteServiceGateway` (also need `manage service-gateways`); `CreateSecurityList`, `DeleteSecurityList` (also need `manage security-lists`); `CreateDhcpOptions`, `DeleteDhcpOptions` (also need `manage dhcp-options`); `CreateDrgAttachment` (also needs `manage drgs`, plus `manage route-tables` if associating a route table on create); `DeleteDrgAttachment` (also needs `manage drgs`). **Note:** All covered by `manage virtual-network-family`. Creating a VCN with a BYOIPv6 prefix requires both `VCN_CREATE` and `BYOIP_RANGE_ASSIGN_TO_VCN`. `AddIpv6VcnCidr` requires both `BYOIP_RANGE_ASSIGN_TO_VCN` and `VCN_UPDATE`. `RemoveIpv6VcnCidr` requires both `BYOIP_RANGE_UNASSIGN_FROM_VCN` and `VCN_UPDATE`. |

#### subnets

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | SUBNET_READ | `ListSubnets`, `GetSubnet` | none |
| read | no extra | no extra | none |
| use | READ + SUBNET_ATTACH, SUBNET_DETACH | no extra | `LaunchInstance` (also needs `use vnics`, `use network-security-groups`, `manage instance-family`); `TerminateInstance` (also needs `manage instance-family`, and `use volumes` if a volume is attached); `AttachVnic` (also needs `manage instances`, `use network-security-groups`, and either `use vnics` or `use instance-family`); `DetachVnic` (also needs `manage instances` and either `use vnics` or `use instance-family`); `CreatePrivateIp`, `DeletePrivateIp` (both also need `use private-ips` and `use vnics`) |
| manage | USE + SUBNET_CREATE, SUBNET_UPDATE, SUBNET_DELETE, SUBNET_MOVE | `ChangeSubnetCompartment` | USE + `CreateSubnet`, `DeleteSubnet` (both also need `manage vcns`, `manage route-tables`, `manage security-lists`, `manage dhcp-options`); `UpdateSubnet` (also needs `manage route-tables` if changing the route table; `manage security-lists` if changing security lists; `manage dhcp-options` if changing DHCP options). **Note:** Covered by `manage virtual-network-family`. |

#### route-tables

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | ROUTE_TABLE_READ | `ListRouteTables`, `GetRouteTable` | none |
| read | no extra | no extra | none |
| use | no extra | no extra | none |
| manage | USE + ROUTE_TABLE_ATTACH, ROUTE_TABLE_DETACH, ROUTE_TABLE_UPDATE, ROUTE_TABLE_CREATE, ROUTE_TABLE_DELETE, ROUTE_TABLE_MOVE | `ChangeRouteTableCompartment` | `CreateRouteTable`, `DeleteRouteTable` (both also need `manage vcns`, `manage internet-gateways`, `manage drgs`, `manage private-ips`, `manage local-peering-gateways`, `use nat-gateways`, `use service-gateways`); `UpdateRouteTable` (also needs `manage internet-gateways`, `manage drgs`, `manage private-ips`, `manage local-peering-gateways`, `use nat-gateways`, `use service-gateways`); `CreateSubnet`, `DeleteSubnet` (also need `manage vcns`, `manage subnets`, `manage security-lists`, `manage dhcp-options`); `UpdateSubnet` (if changing the route table, also needs `manage subnets`). **Note:** All covered by `manage virtual-network-family`. |

#### network-security-groups

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | NETWORK_SECURITY_GROUP_INSPECT | none | `AddNetworkSecurityGroupSecurityRules`, `UpdateNetworkSecurityGroupSecurityRules` (both also need `manage network-security-groups`) |
| read | INSPECT + NETWORK_SECURITY_GROUP_READ | INSPECT + `GetNetworkSecurityGroup`, `ListNetworkSecurityGroups` | no extra |
| use | READ + NETWORK_SECURITY_GROUP_LIST_SECURITY_RULES, NETWORK_SECURITY_GROUP_LIST_MEMBERS, NETWORK_SECURITY_GROUP_UPDATE_MEMBERS | READ + `ListNetworkSecurityGroupSecurityRules`, `ListNetworkSecurityGroupVnics` | READ + `LaunchInstance` (also needs `manage instances`, `read instance-images`, `use vnics`, `use subnets`, `read app-catalog-listing`); `AttachVnic` (also needs `manage instances`, `use subnets`); `UpdateVnic` (also needs `use vnics`) |
| manage | USE + NETWORK_SECURITY_GROUP_UPDATE, NETWORK_SECURITY_GROUP_CREATE, NETWORK_SECURITY_GROUP_DELETE, NETWORK_SECURITY_GROUP_MOVE, NETWORK_SECURITY_GROUP_UPDATE_SECURITY_RULES | USE + `UpdateNetworkSecurityGroup`, `ChangeNetworkSecurityGroupCompartment`, `AddNetworkSecurityGroupSecurityRules`, `UpdateNetworkSecurityGroupSecurityRules`, `RemoveNetworkSecurityGroupSecurityRules` | USE + `CreateNetworkSecurityGroup`, `DeleteNetworkSecurityGroup` (both also need `manage vcns`). **Note:** Covered by `manage virtual-network-family`. |

#### security-lists

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | SECURITY_LIST_READ | `ListSecurityLists`, `GetSecurityList` | none |
| read | no extra | no extra | none |
| use | no extra | no extra | none |
| manage | USE + SECURITY_LIST_ATTACH, SECURITY_LIST_DETACH, SECURITY_LIST_UPDATE, SECURITY_LIST_CREATE, SECURITY_LIST_DELETE, SECURITY_LIST_MOVE | USE + `UpdateSecurityList` (**update is `manage`-only**), `ChangeSecurityListCompartment` | `CreateSecurityList`, `DeleteSecurityList` (both also need `manage vcns`); `CreateSubnet`, `DeleteSubnet` (also need `manage vcns`, `manage subnets`, `manage route-tables`, `manage dhcp-options`); `UpdateSubnet` (if changing security lists, also needs `manage subnets`). **Note:** All covered by `manage virtual-network-family`. |

#### dhcp-options

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | DHCP_READ | `ListDhcpOptions`, `GetDhcpOptions` | none |
| read | no extra | no extra | none |
| use | no extra | no extra | none |
| manage | USE + DHCP_ATTACH, DHCP_DETACH, DHCP_UPDATE, DHCP_CREATE, DHCP_DELETE, DHCP_MOVE | USE + `UpdateDhcpOptions` (**update is `manage`-only**), `ChangeDhcpOptionsCompartment` | USE + `CreateDhcpOptions`, `DeleteDhcpOptions` (both also need `manage vcns`); `CreateSubnet`, `DeleteSubnet` (also need `manage vcns`, `manage subnets`, `manage route-tables`, `manage security-lists`); `UpdateSubnet` (if changing DHCP options, also needs `manage subnets`). **Note:** All covered by `manage virtual-network-family`. |

#### private-ips

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | PRIVATE_IP_READ | `ListPrivateIps`, `GetPrivateIp` | For ephemeral public IPs only: `ListPublicIps`, `GetPublicIpByPrivateIpId`, `GetPublicIpByIpAddress` |
| read | no extra | no extra | none |
| use | READ + PRIVATE_IP_UPDATE, PRIVATE_IP_ASSIGN, PRIVATE_IP_UNASSIGN, PRIVATE_IP_CREATE, PRIVATE_IP_DELETE, PRIVATE_IP_ASSIGN_PUBLIC_IP, PRIVATE_IP_UNASSIGN_PUBLIC_IP | READ + for ephemeral public IPs: `UpdatePublicIp`, `BulkUpdatePrivateIps`, `CreatePublicIp`, `BulkCreatePrivateIps`, `DeletePublicIp`, `BulkDeletePrivateIps` | `CreatePrivateIp`, `BulkCreatePrivateIps`, `DeletePrivateIp`, `BulkDeletePrivateIps` (these also need `use subnets` and `use vnics`); `UpdatePrivateIp`, `BulkUpdatePrivateIps` (also need `use vnics`); for reserved public IPs: `UpdatePublicIp`, `BulkUpdatePrivateIps`, `CreatePublicIp`, `BulkCreatePrivateIps`, `DeletePublicIp`, `BulkDeletePrivateIps` (all also need `manage public-ips`). **Note:** Covered by `use virtual-network-family`. |
| manage | USE + PRIVATE_IP_ROUTE_TABLE_ATTACH, PRIVATE_IP_ROUTE_TABLE_DETACH | no extra | USE + `CreateRouteTable`, `DeleteRouteTable` (both also need `manage vcns`, `manage internet-gateways`, `manage drgs`, `manage route-tables`, `manage local-peering-gateways`, `use nat-gateways`, `use service-gateways`); `UpdateRouteTable` (also needs `manage internet-gateways`, `manage drgs`, `manage route-tables`, `manage local-peering-gateways`, `use nat-gateways`, `use service-gateways`). **Note:** Covered by `manage virtual-network-family`. |

#### public-ips

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | none | none | none |
| read | PUBLIC_IP_READ | For reserved public IPs only: `ListPublicIps`, `GetPublicIpByPrivateIpId`, `GetPublicIpByIpAddress` | Listing/getting ephemeral public IPs uses `private-ip` permissions. |
| use | READ + PUBLIC_IP_ASSIGN_PRIVATE_IP, PUBLIC_IP_UNASSIGN_PRIVATE_IP | no extra | For reserved public IPs: `UpdatePublicIp`, `CreatePublicIp`, `DeletePublicIp` (all also need `use private-ips` and `manage public-ips`). **Note:** Covered by `manage virtual-network-family`. |
| manage | USE + PUBLIC_IP_UPDATE, PUBLIC_IP_CREATE, PUBLIC_IP_DELETE | no extra | USE + for reserved public IPs: `UpdatePublicIp`, `CreatePublicIp`, `DeletePublicIp` (all also need `use private-ips`). **Note:** Covered by `manage virtual-network-family`. |

#### byoiprange

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | BYOIP_RANGE_INSPECT | `ListByoipRanges` | none |
| read | INSPECT + BYOIP_RANGE_READ | `GetByoipRange`, `ListByoipAllocatedRanges` | none |
| use | READ + BYOIP_RANGE_ADD_CAPACITY_FROM | `AddPublicIpPoolCapacity` | none |
| manage | USE + BYOIP_RANGE_CREATE, BYOIP_RANGE_DELETE, BYOIP_RANGE_UPDATE, BYOIP_RANGE_VALIDATE, BYOIP_RANGE_ADVERTISE, BYOIP_RANGE_WITHDRAW, BYOIP_RANGE_MOVE, BYOIP_RANGE_ASSIGN_TO_VCN, BYOIP_RANGE_UNASSIGN_FROM_VCN | `CreateByoipRange`, `DeleteByoipRange`, `UpdateByoipRange`, `ValidateByoipRange`, `AdvertiseByoipRange`, `WithdrawByoipRange`, `ChangeByoipRangeCompartment`, `AddIpv6VcnCidr`, `RemoveIpv6VcnCidr` | Creating a VCN with a BYOIPv6 prefix needs `VCN_CREATE` and `BYOIP_RANGE_ASSIGN_TO_VCN`. `AddIpv6VcnCidr` needs `BYOIP_RANGE_ASSIGN_TO_VCN` and `VCN_UPDATE`. `RemoveIpv6VcnCidr` needs `BYOIP_RANGE_UNASSIGN_FROM_VCN` and `VCN_UPDATE`. |

#### publicippool

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | PUBLIC_IP_POOL_INSPECT | `ListPublicIpPool` | none |
| read | INSPECT + PUBLIC_IP_POOL_READ | `ReadPublicIpPool` | none |
| use | READ + PUBLIC_IP_POOL_CREATE_PUBLIC_IP_FROM | `CreatePublicIpPool` | none |
| manage | USE + PUBLIC_IP_POOL_CREATE, PUBLIC_IP_POOL_DELETE, PUBLIC_IP_POOL_UPDATE, PUBLIC_IP_POOL_ADD_CAPACITY, PUBLIC_IP_POOL_REMOVE_CAPACITY, PUBLIC_IP_POOL_MOVE | `CreatePublicIp`, `DeletePublicIpPool`, `UpdatePublicIpPool`, `AddPublicIpPoolCapacity`, `RemovePublicIpPoolCapacity`, `ChangePublicIpPoolCompartment` | none |

#### ipv6s

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | none | none | none |
| read | IPV6_READ | `GetIpv6`, `ListIpv6s` (also need `inspect vnics` and `inspect subnets` to list by VNIC / subnet). **Note:** Covered by `use virtual-network-family`. | none |
| use | no extra | no extra | no extra |
| manage | USE + IPV6_UPDATE, IPV6_CREATE, IPV6_DELETE | no extra | USE + `UpdateIpv6`, `BulkUpdateIpv6s` (also need `use vnics`); `CreateIpv6`, `BulkCreateIpv6s`; `DeleteIpv6`, `BulkDeleteIpv6s` (these also need `use vnics` and `use subnets`). **Note:** Covered by `manage virtual-network-family`. |

#### internet-gateways

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | INTERNET_GATEWAY_READ | `ListInternetGateways`, `GetInternetGateway` | none |
| read | no extra | no extra | none |
| use | no extra | no extra | none |
| manage | USE + INTERNET_GATEWAY_ATTACH, INTERNET_GATEWAY_DETACH, INTERNET_GATEWAY_UPDATE, INTERNET_GATEWAY_CREATE, INTERNET_GATEWAY_DELETE, INTERNET_GATEWAY_MOVE | USE + `UpdateInternetGateway` (**update is `manage`-only**), `ChangeInternetGatewayCompartment` | `CreateInternetGateway`, `DeleteInternetGateway` (both also need `manage vcns`); `CreateRouteTable`, `DeleteRouteTable` (both also need `manage route-tables`, `manage vcns`, `manage drgs`, `manage private-ips`, `manage local-peering-gateways`, `use nat-gateways`, `use service-gateways`); `UpdateRouteTable` (also needs `manage route-tables`, `manage drgs`, `manage private-ips`, `manage local-peering-gateways`, `use nat-gateways`, `use service-gateways`). **Note:** All covered by `manage virtual-network-family`. |

#### nat-gateways

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | none | none | none |
| read | NAT_GATEWAY_READ | `ListNatGateways`, `GetNatGateway` | none |
| use | READ + NAT_GATEWAY_ATTACH, NAT_GATEWAY_DETACH | no extra | READ + `CreateRouteTable`, `DeleteRouteTable` (both also need `manage route-tables`, `manage vcns`, `manage drgs`, `manage private-ips`, `manage internet-gateways`, `manage local-peering-gateways`, `use service-gateways`); `UpdateRouteTable` (also needs `manage route-tables`, `manage drgs`, `manage private-ips`, `manage internet-gateways`, `manage local-peering-gateways`, `use service-gateways`). **Note:** Covered by `manage virtual-network-family`. |
| manage | USE + NAT_GATEWAY_UPDATE, NAT_GATEWAY_CREATE, NAT_GATEWAY_DELETE, NAT_GATEWAY_MOVE | USE + `UpdateNatGateway`, `ChangeNatGatewayCompartment` (**update is `manage`-only**) | `CreateNatGateway`, `DeleteNatGateway` (both also need `manage vcns`). **Note:** Covered by `manage virtual-network-family`. |

#### service-gateways

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | SERVICE_GATEWAY_READ | `ListServiceGateways`, `GetServiceGateway` | none |
| read | no extra | no extra | no extra |
| use | READ + SERVICE_GATEWAY_ATTACH, SERVICE_GATEWAY_DETACH | no extra | READ + `CreateRouteTable`, `DeleteRouteTable` (both also need `manage route-tables`, `manage vcns`, `manage internet-gateways`, `manage drgs`, `manage private-ips`, `manage local-peering-gateways`); `UpdateRouteTable` (also needs `manage route-tables`, `manage drgs`, `manage internet-gateways`, `manage private-ips`, `manage local-peering-gateways`) |
| manage | USE + SERVICE_GATEWAY_UPDATE, SERVICE_GATEWAY_CREATE, SERVICE_GATEWAY_DELETE, SERVICE_GATEWAY_ADD_SERVICE, SERVICE_GATEWAY_DELETE_SERVICE, SERVICE_GATEWAY_MOVE | USE + `ChangeServiceGatewayCompartment`, `AttachServiceId`, `DetachServiceId` (**update is `manage`-only**) | `CreateServiceGateway` (also needs `manage vcns`, plus `manage route-tables` if associating a route table on create); `UpdateServiceGateway` (also needs `manage route-tables` if associating a route table on update); `DeleteServiceGateway` (also needs `manage vcns`). **Note:** All covered by `manage virtual-network-family`. |

#### local-peering-gateways

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | LOCAL_PEERING_GATEWAY_READ | `ListLocalPeeringGateways`, `GetLocalPeeringGateway` | none |
| read | no extra | no extra | none |
| use | no extra | no extra | none |
| manage | USE + LOCAL_PEERING_GATEWAY_UPDATE, LOCAL_PEERING_GATEWAY_ATTACH, LOCAL_PEERING_GATEWAY_DETACH, LOCAL_PEERING_GATEWAY_CREATE, LOCAL_PEERING_GATEWAY_DELETE, LOCAL_PEERING_GATEWAY_MOVE | `ChangeLocalPeeringGatewayCompartment` | `CreateLocalPeeringGateway` (also needs `manage vcns`, plus `manage route-tables` if associating a route table on create); `UpdateLocalPeeringGateway` (also needs `manage route-tables` if associating a route table on update); `DeleteLocalPeeringGateway` (also needs `manage vcns`); `CreateRouteTable`, `DeleteRouteTable` (also need `manage route-tables`, `manage vcns`, `manage internet-gateways`, `manage drgs`, `manage private-ips`, `use nat-gateways`, `use service-gateways`); `UpdateRouteTable` (also needs `manage route-tables`, `manage internet-gateways`, `manage drgs`, `manage private-ips`, `use nat-gateways`, `use service-gateways`). **Note:** Covered by `manage virtual-network-family`. |

#### local-peering-from

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | LOCAL_PEERING_GATEWAY_READ | none | none |
| read / use | no extra | none | none |
| manage | USE + LOCAL_PEERING_GATEWAY_CONNECT_FROM | no extra | `ConnectLocalPeeringGateways` (the acceptor must grant the requestor `manage local-peering-to` in the acceptor's compartment). **Note:** Covered by `manage virtual-network-family`. |

#### local-peering-to

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | LOCAL_PEERING_GATEWAY_READ | none | none |
| read / use | no extra | none | none |
| manage | USE + LOCAL_PEERING_GATEWAY_CONNECT_TO | no extra | `ConnectLocalPeeringGateways` (requestor must have `manage local-peering-from` in its own compartment). **Note:** Covered by `manage virtual-network-family`. |

#### remote-peering-connections

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | REMOTE_PEERING_CONNECTION_READ | `ListRemotePeeringConnections`, `GetRemotePeeringConnection` | none |
| read / use | no extra | no extra | none |
| manage | USE + REMOTE_PEERING_CONNECTION_UPDATE, REMOTE_PEERING_CONNECTION_CREATE, REMOTE_PEERING_CONNECTION_DELETE, REMOTE_PEERING_CONNECTION_RESOURCE_MOVE | `UpdateRemotePeeringConnection`, `ChangeRemotePeeringConnectionCompartment` | `CreateRemotePeeringConnection`, `DeleteRemotePeeringConnection` (both also need `manage drgs`). **Note:** Covered by `manage virtual-network-family`. |

#### remote-peering-from / remote-peering-to

Analogous to `local-peering-from` / `local-peering-to`, but with `REMOTE_PEERING_CONNECTION_CONNECT_FROM` / `REMOTE_PEERING_CONNECTION_CONNECT_TO`, and driving `ConnectRemotePeeringConnections`.

#### drgs (drg-object)

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | DRG_READ | `GetDrg`, `ListDrgs`, `GetAllDrgAttachments` | none |
| read | no extra | no extra | none |
| use | READ + DRG_ATTACH, DRG_DETACH | no extra | `CreateDrgAttachment` (also needs `manage vcns`, plus `manage route-tables` if associating a VCN route table, plus `manage drg-route-tables` if assigning a DRG route table); `DeleteDrgAttachment` (also needs `manage vcns`) |
| manage | USE + DRG_UPDATE, DRG_CREATE, DRG_DELETE, DRG_MOVE | USE + `CreateDrg`, `DeleteDrg`, `UpdateDrg`, `UpgradeDrg`, `ChangeDrgCompartment` | none |

#### drg-attachment

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | DRG_ATTACHMENT_READ | `ListDrgAttachments`, `GetDrgAttachment` | none |
| read / use | no extra | no extra | none |
| manage | USE + DRG_ATTACHMENT_UPDATE | USE + `RemoveExportDrgRouteDistribution` (also needs `manage drg-route-distribution`); `UpdateDrgAttachment` (also needs `manage route-tables` if associating a VCN route table, plus `manage drg-route-tables` if assigning a DRG route table). **Note:** Covered by `manage virtual-network-family`. | |

#### drg-route-table

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | DRG_ROUTE_TABLE_READ, DRG_ROUTE_RULE_READ | `GetDrgRouteTable`, `ListDrgRouteRules` | none |
| read / use | READ+DRG_ROUTE_TABLE_ATTACH | no extra | For assigning a DRG route table to a DRG attachment: `CreateDrgAttachment`, `UpdateDrgAttachment` (both also need `manage drg-attachment`) |
| manage | USE + DRG_ROUTE_TABLE_CREATE, DRG_ROUTE_TABLE_DELETE, DRG_ROUTE_TABLE_UPDATE, DRG_ROUTE_RULE_UPDATE | USE + `CreateDrgRouteTable`, `DeleteDrgRouteTable`, `UpdateDrgRouteTable`, `UpdateDrgRouteRules`, `RemoveDrgRouteRules`, `AddDrgRouteRules`, `RemoveImportDrgRouteDistribution` (also needs `manage drg-route-table`) | |

#### drg-route-distribution

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | DRG_ROUTE_DISTRIBUTION_READ, DRG_ROUTE_DISTRIBUTION_STATEMENT_READ | `GetDrgRouteDistribution`, `ListDrgRouteDistributions`, `ListDrgRouteDistributionStatements` | none |
| read | no extra | no extra | none |
| use | DRG_ROUTE_DISTRIBUTION_ASSIGN | no extra | `UpdateDrgRouteTable`, `CreateDrgRouteTable` (also need `manage drg-route-table` to assign the distribution); `RemoveExportDrgRouteDistribution` (also needs `manage drg-attachment`); `RemoveImportDrgRouteDistribution` (also needs `manage drg-route-table`) |
| manage | USE + DRG_ROUTE_DISTRIBUTION_UPDATE, DRG_ROUTE_DISTRIBUTION_CREATE, DRG_ROUTE_DISTRIBUTION_DELETE, DRG_ROUTE_DISTRIBUTION_STATEMENT_UPDATE | USE + `UpdateDrgRouteDistribution`, `CreateDrgRouteDistribution`, `DeleteDrgRouteDistribution`, `UpdateDrgRouteDistributionStatements`, `RemoveDrgRouteDistributionStatements`, `AddDrgRouteDistributionStatements` | none |

#### cpes

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | CPE_READ | `ListCpes`, `GetCpe` | none |
| read / use | no extra | no extra | none |
| manage | USE + CPE_ATTACH, CPE_DETACH, CPE_UPDATE, CPE_CREATE, CPE_DELETE, CPE_RESOURCE_MOVE | USE + `CreateCpe`, `UpdateCpe`, `DeleteCpe`, `ChangeCpeCompartment` | `CreateIPSecConnection`, `DeleteIPSecConnection` (both also need `manage ipsec-connections` and `manage drgs`). **Note:** Covered by `manage virtual-network-family`. |

#### ipsec (ipsec-connections)

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | IPSEC_CONNECTION_READ | `ListIPSecConnections`, `GetIPSecConnection`, `GetIPSecConnectionStatus`, `ListIPSecConnectionTunnels`, `GetIPSecConnectionTunnel`, `GetTunnelCpeDeviceConfig`, `GetTunnelCpeDeviceTemplateContent`, `GetCpeDeviceTemplateContent`, `GetIpsecCpeDeviceTemplateContent` | none |
| read | INSPECT + IPSEC_CONNECTION_DEVICE_CONFIG_READ | INSPECT + `GetIPSecConnectionDeviceConfig`, `GetIPSecConnectionTunnelSharedSecret` | none |
| use | no extra | no extra | none |
| manage | USE + IPSEC_CONNECTION_CREATE, IPSEC_CONNECTION_UPDATE, IPSEC_CONNECTION_DELETE, IPSEC_CONNECTION_DEVICE_CONFIG_UPDATE | USE + `UpdateIPSecConnection`, `UpdateTunnelCpeDeviceConfig`, `UpdateIPSecConnectionTunnel` | `CreateIPSecConnection`, `DeleteIPSecConnection` (both also need `manage cpes` and `manage drgs`). **Note:** Covered by `manage virtual-network-family`. |

#### ipam

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | IPAM_READ | `ListIpInventory`, `GetVcnOverlap`, `GetSubnetIpInventory`, `GetSubnetCidrUtilization` | none |

#### capture-filters

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | CAPTURE_FILTER_LIST | `ListCaptureFilters` | none |
| read | INSPECT + CAPTURE_FILTER_READ | `GetCaptureFilter` | none |
| use | READ + CAPTURE_FILTER_UPDATE, CAPTURE_FILTER_ATTACH, CAPTURE_FILTER_DETACH | `UpdateCaptureFilter` | none |
| manage | USE + CAPTURE_FILTER_CREATE, CAPTURE_FILTER_DELETE, CAPTURE_FILTER_MOVE | `ChangeCaptureFilterCompartment` | `CreateCaptureFilter` requires `CAPTURE_FILTER_CREATE` + `VCN_ATTACH`; `DeleteCaptureFilter` requires `CAPTURE_FILTER_DELETE` + `VCN_DETACH`. **Note:** Covered by `manage virtual-network-family`. |

#### cross-connects

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | CROSS_CONNECT_READ | `ListCrossConnects`, `GetCrossConnect` | none |
| read / use | no extra | no extra | none |
| manage | USE + CROSS_CONNECT_UPDATE, CROSS_CONNECT_CREATE, CROSS_CONNECT_DELETE, CROSS_CONNECT_RESOURCE_MOVE, CROSS_CONNECT_ATTACH, CROSS_CONNECT_DETACH | `UpdateCrossConnect`, `CreateCrossConnect`, `DeleteCrossConnect`, `ChangeCrossConnectCompartment` | `UpdateVirtualCircuit` (also needs `use virtual-circuits`); `CreateVirtualCircuit`, `DeleteVirtualCircuit` (also need `manage virtual-circuits`) |

#### cross-connect-groups

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | CROSS_CONNECT_GROUP_READ | `ListCrossConnectGroups`, `GetCrossConnectGroup` | none |
| read / use | no extra | no extra | none |
| manage | USE + CROSS_CONNECT_GROUP_UPDATE, CROSS_CONNECT_GROUP_CREATE, CROSS_CONNECT_GROUP_DELETE, CROSS_CONNECT_GROUP_RESOURCE_MOVE | `UpdateCrossConnectGroup`, `CreateCrossConnectGroup`, `DeleteCrossConnectGroup`, `ChangeCrossConnectGroupCompartment` | no extra |

#### virtual-circuits

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VIRTUAL_CIRCUIT_READ | `ListVirtualCircuits`, `GetVirtualCircuit` | none |
| read | no extra | no extra | none |
| use | READ + VIRTUAL_CIRCUIT_UPDATE | no extra | `UpdateVirtualCircuit` (also needs `manage drgs`, plus `manage cross-connects` if changing the cross-connect) |
| manage | USE + VIRTUAL_CIRCUIT_CREATE, VIRTUAL_CIRCUIT_DELETE, VIRTUAL_CIRCUIT_RESOURCE_MOVE | `ChangeVirtualCircuitCompartment` | USE + `CreateVirtualCircuit`, `DeleteVirtualCircuit` (both also need `manage drgs`, plus `manage cross-connects` if mapping to a specific cross-connect). **Note:** Covered by `manage virtual-network-family`. |

#### vnics

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VNIC_READ | `GetVnic` | `CreateInstanceConfiguration` (if using `CreateInstanceConfigurationFromInstanceDetails`; also needs `read instances`, `inspect vnic-attachments`, `inspect volumes`, `inspect volume-attachments`) |
| read | no extra | no extra | none |
| use | READ + VNIC_ATTACH, VNIC_DETACH, VNIC_CREATE, VNIC_DELETE, VNIC_UPDATE, VNIC_ASSOCIATE_NETWORK_SECURITY_GROUP, VNIC_DISASSOCIATE_NETWORK_SECURITY_GROUP | no extra | READ + `LaunchInstance` (also needs `use subnets`, `use network-security-groups`, `manage instance-family`); `AttachVnic` (also needs `manage instances`, `use subnets`, `use network-security-groups`); `UpdateVnic` (also needs `use network-security-groups`); `DetachVnic` (also needs `manage instances` and `use subnets`); `CreatePrivateIp`, `DeletePrivateIp` (both also need `use subnets` and `use private-ips`) |
| manage | no extra | no extra | no extra |

#### vnic-attachments

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VNIC_ATTACHMENT_READ | `GetVnicAttachment` | `ListVnicAttachments` (also needs `inspect instances`); `CreateInstanceConfiguration` (if using `CreateInstanceConfigurationFromInstanceDetails`; also needs `read instances`, `inspect vnics`, `inspect volumes`, `inspect volume-attachments`) |
| read / use / manage | no extra | none | no extra |

#### vtaps

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VTAP_LIST | `ListVtaps` | none |
| read | INSPECT + VTAP_READ | `GetVtap` | none |
| use | READ + VTAP_UPDATE | none | `UpdateVtap` (requires VTAP_UPDATE + attach/detach on CAPTURE_FILTER, NLB_VTAP_TARGET, VNIC, or LB/DB_SYSTEM/EXADATA_VM_CLUSTER/ADW VTAP ENABLE/DISABLE depending on source/target). **Note:** Covered by `manage virtual-network-family`. |
| manage | USE + VTAP_CREATE, VTAP_DELETE, VTAP_MOVE | `ChangeVtapCompartment` | `CreateVtap` (requires VTAP_CREATE + CAPTURE_FILTER_ATTACH + VCN_ATTACH); `DeleteVtap` (requires VTAP_DELETE + CAPTURE_FILTER_DETACH + VCN_DETACH + appropriate source detach/disable). **Note:** Covered by `manage virtual-network-family`. |

#### vlans

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VLAN_READ | `ListVlans`, `GetVlan` | none |
| read | no extra | no extra | none |
| use | READ + no extra | `UpdateVlan` | none |
| manage | USE + VLAN_CREATE, VLAN_DELETE, VLAN_ASSOCIATE_NETWORK_SECURITY_GROUP, VLAN_DISASSOCIATE_NETWORK_SECURITY_GROUP, VLAN_MOVE | `ChangeVlanCompartment` | USE + `CreateVlan`, `DeleteVlan` (both also need `manage vcns`, `manage route-tables`, `manage security-lists`). **Note:** Covered by `manage virtual-network-family`. |

### For `instance-family` Resource Types

`instance-family` includes extra permissions beyond the sum of its members so a single statement covers common "instance with attached volume" use cases. Extra permissions granted by verb:

- `inspect instance-family`: `VNIC_READ`, `VNIC_ATTACHMENT_READ`, `VOLUME_ATTACHMENT_INSPECT`
- `read instance-family`: `VOLUME_ATTACHMENT_READ`
- `use instance-family`: `VNIC_ATTACH`, `VNIC_DETACH`, `VOLUME_ATTACHMENT_UPDATE`
- `manage instance-family`: `VOLUME_ATTACHMENT_CREATE`, `VOLUME_ATTACHMENT_DELETE`

#### instances

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | INSTANCE_INSPECT | none | `GetConsoleHistory`, `ListConsoleHistories` (both also need `inspect console-histories`); `ListVnicAttachments` (also needs `inspect vnic-attachments`); `ListVolumeAttachments`, `GetVolumeAttachments` (also need `inspect volumes` and `inspect volume-attachments`) |
| read | INSPECT + INSTANCE_READ | `ListInstances` (to list instances in a compute cluster, also needs `read compute-clusters`), `ListInstanceDevices`, `GetInstance`, `GetInstanceMaintenanceReboot` (`ListInstances` and `GetInstance` include any user-provided metadata). | INSPECT + `CaptureConsoleHistory` (also needs `manage console-histories` and `read instance-images`); `ShowConsoleHistoryData` (also needs `read console-histories` and `read instance-images`); `CreateInstanceConfiguration` (if using `CreateInstanceConfigurationFromInstanceDetails`; also needs `inspect vnics`, `inspect vnic-attachments`, `inspect volumes`, `inspect volume-attachments`) |
| use | READ + INSTANCE_UPDATE, INSTANCE_CREATE_IMAGE, INSTANCE_POWER_ACTIONS, INSTANCE_ATTACH_VOLUME, INSTANCE_DETACH_VOLUME | READ + `UpdateInstance`, `InstanceAction` | READ + `CreateImage` (also needs `manage instance-images`); `AttachVolume`, `DetachVolume` (both also need `manage volume-attachments` and `use volumes`) |
| manage | USE + INSTANCE_CREATE, INSTANCE_DELETE, INSTANCE_ATTACH_SECONDARY_VNIC, INSTANCE_DETACH_SECONDARY_VNIC, INSTANCE_MOVE | `ChangeInstanceCompartment` | USE + `LaunchInstance` (also needs `read instance-images`, `use vnics`, `use subnets`, `use network-security-groups`, `read app-catalog-listing`; for Console, also `inspect vcns`; for compute clusters, also `use compute-clusters`); `TerminateInstance` (also needs `use vnics`, `use subnets`, and — if a volume is attached — `manage volume-attachments` and `use volumes`); `AttachVnic` (also needs `use subnets`, `use network-security-groups`, and either `use vnics` or `use instance-family`); `DetachVnic` (also needs `use subnets` and either `use vnics` or `use instance-family`); `GetWorkRequest`, `ListWorkRequestErrors`, `ListWorkRequestLogs` (for `instances`-related work requests; all also need the permissions for `LaunchInstance`) |

#### console-histories

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | CONSOLE_HISTORY_INSPECT | none | `ListConsoleHistories`, `GetConsoleHistory` (both also need `inspect instances`) |
| read | INSPECT + CONSOLE_HISTORY_READ | none | INSPECT + `ShowConsoleHistoryData` (also needs `read instances` and `read instance-images`) |
| use | no extra | none | no extra |
| manage | USE + CONSOLE_HISTORY_CREATE, CONSOLE_HISTORY_DELETE | `DeleteConsoleHistory` | USE + `CaptureConsoleHistory` (also needs `read instances` and `read instance-images`) |

#### instance-console-connection

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | INSTANCE_CONSOLE_CONNECTION_INSPECT | none | `ListInstanceConsoleConnections` (also needs `inspect instances` and `read instances`) |
| read | INSPECT + INSTANCE_CONSOLE_CONNECTION_READ | none | INSPECT + `GetInstanceConsoleConnection` (also needs `read instances`) |
| use | READ + none | no extra | |
| manage | USE + INSTANCE_CONSOLE_CONNECTION_CREATE, INSTANCE_CONSOLE_CONNECTION_DELETE | `DeleteInstanceConsoleConnection`, `UpdateInstanceConsoleConnection` | `CreateInstanceConsoleConnection` (also needs `read instances`) |

#### instance-images

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | INSTANCE_IMAGE_INSPECT | `ListImages`, `GetImage` | none |
| read | INSPECT + INSTANCE_IMAGE_READ | no extra | INSPECT + `LaunchInstance` (also needs `manage instances`, `use vnics`, `use subnets`, `use network-security-groups`); `CaptureConsoleHistory` (also needs `read instances` and `manage console-histories`); `ShowConsoleHistoryData` (also needs `read instances` and `read console-histories`) |
| use | READ + INSTANCE_IMAGE_UPDATE | `UpdateImage` | no extra |
| manage | USE + INSTANCE_IMAGE_CREATE, INSTANCE_IMAGE_DELETE, INSTANCE_IMAGE_MOVE | `DeleteImage`, `ChangeImageCompartment` | USE + `CreateImage` (also needs `use instances`); `GetWorkRequest`, `ListWorkRequestErrors`, `ListWorkRequestLogs` (for `instance-images`-related work requests; all also need `CreateImage` perms) |

#### app-catalog-listing

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | APP_CATALOG_LISTING_INSPECT | `ListAppCatalogSubscriptions` | none |
| read | INSPECT + APP_CATALOG_LISTING_READ | no extra | INSPECT + `LaunchInstance` (also needs `use instances`, `read instance-images`, `use vnics`, `use subnets`, `use network-security-groups`) |
| manage | READ + APP_CATALOG_LISTING_SUBSCRIBE | READ + `CreateAppCatalogSubscription`, `DeleteAppCatalogSubscription` | none |

### For `compute-management-family` Resource Types

#### instance-configurations

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | INSTANCE_CONFIGURATION_INSPECT | `ListInstanceConfigurations` | none |
| read | INSPECT + INSTANCE_CONFIGURATION_READ | INSPECT + `GetInstanceConfiguration` | none |
| use | no extra | no extra | none |
| manage | USE + INSTANCE_CONFIGURATION_CREATE, INSTANCE_CONFIGURATION_UPDATE, INSTANCE_CONFIGURATION_LAUNCH, INSTANCE_CONFIGURATION_DELETE, INSTANCE_CONFIGURATION_MOVE | USE + `CreateInstanceConfiguration` (with `CreateInstanceConfigurationDetails` subtype), `UpdateInstanceConfiguration`, `LaunchInstanceConfiguration`, `DeleteInstanceConfiguration`, `ChangeInstanceConfigurationCompartment` | none |

#### instance-pools

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | INSTANCE_POOL_INSPECT | `ListInstancePools` | none |
| read | INSPECT + INSTANCE_POOL_READ | INSPECT + `GetInstancePool`, `ListInstancePoolInstances` | none |
| use | READ + INSTANCE_POOL_POWER_ACTIONS | no extra | `ResetInstancePool`, `SoftresetInstancePool`, `StartInstancePool`, `StopInstancePool` (all also need `use instances`) |
| manage | USE + INSTANCE_POOL_CREATE, INSTANCE_POOL_UPDATE, INSTANCE_POOL_DELETE, INSTANCE_POOL_MOVE, INSTANCE_POOL_INSTANCE_ATTACH, INSTANCE_POOL_INSTANCE_DETACH | USE + `UpdateInstancePool`, `ChangeInstancePoolCompartment`, `AttachInstancePoolInstance`, `DetachInstancePoolInstance` | USE + `CreateInstancePool` (also needs `manage instances`, `read instance-images`, `use vnics`, `use subnets`); `TerminateInstancePool` (also needs `manage instances`, `use vnics`, `use subnets`, `manage volume-attachments`, `use volumes`); work-request APIs for the pool |

#### cluster-networks

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | CLUSTER_NETWORK_INSPECT | `ListClusterNetworks` | none |
| read | INSPECT + CLUSTER_NETWORK_READ | INSPECT + `GetClusterNetwork`, `ListClusterNetworkInstances` (also needs `read instance-pools`) | none |
| use | no extra | no extra | no extra |
| manage | USE + CLUSTER_NETWORK_CREATE, CLUSTER_NETWORK_UPDATE, CLUSTER_NETWORK_DELETE, CLUSTER_NETWORK_MOVE | USE + `UpdateClusterNetwork`, `ChangeClusterNetworkCompartment` | USE + `CreateClusterNetwork` (also needs `manage instances`, `manage instance-pools`, `read instance-images`, `use vnics`, `use subnets`); `TerminateClusterNetwork` (also needs `manage instances`, `manage instance-pools`, `use vnics`, `use subnets`, `manage volume-attachments`, `use volumes`); work-request APIs |

### For `instance-agent-command-family` and `instance-agent-family`

#### instance-agent-commands

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | INSTANCE_AGENT_COMMAND_INSPECT | `ListInstanceAgentCommands` (to view in Console, also needs `read instances`) | none |
| read | INSPECT + INSTANCE_AGENT_COMMAND_READ, INSTANCE_AGENT_COMMAND_EXECUTION_INSPECT | INSPECT + `GetInstanceAgentCommand`, `GetInstanceAgentCommandExecution`, `ListInstanceAgentCommandExecutions` | none |
| use | READ + INSTANCE_AGENT_COMMAND_CREATE, INSTANCE_AGENT_COMMAND_DELETE | READ + `CreateInstanceAgentCommand`, `CancelInstanceAgentCommand` | none |
| manage | no extra | no extra | none |

#### instance-agent-plugins

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | INSTANCE_AGENT_PLUGIN_INSPECT | `ListInstanceAgentPlugins`, `ListInstanceagentAvailablePlugins` | none |
| read | INSPECT + INSTANCE_AGENT_PLUGIN_READ | INSPECT + `GetInstanceAgentPlugin` (to view in Console, also needs `read instances`) | none |
| use / manage | no extra | no extra | none |

### For Additional Compute Individual Resource Types

#### auto-scaling-configurations

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | AUTO_SCALING_CONFIGURATION_INSPECT | `ListAutoScalingConfigurations`, `ListAutoScalingPolicies` | none |
| read | INSPECT + AUTO_SCALING_CONFIGURATION_READ | INSPECT + `GetAutoScalingConfiguration`, `GetAutoScalingPolicy` | none |
| use | no extra | no extra | none |
| manage | USE + AUTO_SCALING_CONFIGURATION_CREATE, AUTO_SCALING_CONFIGURATION_UPDATE, AUTO_SCALING_CONFIGURATION_DELETE, AUTO_SCALING_CONFIGURATION_MOVE | USE + `ChangeAutoScalingConfigurationCompartment` | USE + `CreateAutoScalingConfiguration`, `UpdateAutoScalingConfiguration`, `DeleteAutoScalingConfiguration`, `CreateAutoScalingPolicy`, `UpdateAutoScalingPolicy`, `DeleteAutoScalingPolicy` (all also need `manage instance-pools`) |

#### compute-capacity-reports

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| manage | COMPUTE_CAPACITY_REPORT_CREATE | `CreateComputeCapacityReport` | none |

#### compute-capacity-reservations

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | CAPACITY_RESERVATION_INSPECT | `ListComputeCapacityReservations`, `ListComputeCapacityReservationInstanceShapes` | none |
| read | INSPECT + CAPACITY_RESERVATION_READ | INSPECT + `GetComputeCapacityReservation`, `ListComputeCapacityReservationInstances` | none |
| use | READ + CAPACITY_RESERVATION_LAUNCH_INSTANCE, CAPACITY_RESERVATION_UPDATE | none | READ + `LaunchInstance` (also needs `use subnets`, `use network-security-groups`, `manage instance-family`) |
| manage | USE + CAPACITY_RESERVATION_CREATE, CAPACITY_RESERVATION_UPDATE, CAPACITY_RESERVATION_DELETE, CAPACITY_RESERVATION_MOVE | USE + `CreateComputeCapacityReservation`, `UpdateComputeCapacityReservation`, `DeleteComputeCapacityReservation`, `ChangeComputeCapacityReservationCompartment` | none |

#### compute-clusters

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | COMPUTE_CLUSTER_INSPECT | `ListComputeClusters` | none |
| read | INSPECT + COMPUTE_CLUSTER_READ | INSPECT + `GetComputeCluster` | none |
| use | READ + COMPUTE_CLUSTER_UPDATE, COMPUTE_CLUSTER_LAUNCH_INSTANCE | READ + `UpdateComputeCluster` | READ + `LaunchInstance` (also needs `read instance-images`, `use vnics`, `use subnets`, `use network-security-groups`, `read app-catalog-listing`; for Console, also `inspect vcns`) |
| manage | USE + COMPUTE_CLUSTER_CREATE, COMPUTE_CLUSTER_MOVE, COMPUTE_CLUSTER_DELETE | USE + `CreateComputeCluster`, `ChangeComputeClusterCompartment`, `DeleteComputeCluster` | no extra |

#### dedicated-vm-hosts

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | DEDICATED_VM_HOST_INSPECT | `ListDedicatedVmHosts` | none |
| read | INSPECT + DEDICATED_VM_HOST_READ | INSPECT + `GetDedicatedVmHost`, `ListDedicatedVmHostInstances` | none |
| use | READ + DEDICATED_VM_HOST_LAUNCH_INSTANCE, DEDICATED_VM_HOST_UPDATE | READ + `UpdateDedicatedVmHost` | READ + `LaunchInstance` (also needs `create instance` in the target compartment and `dedicated vm host launch instance` in the DVH compartment) |
| manage | USE + DEDICATED_VM_HOST_CREATE, DEDICATED_VM_HOST_MOVE, DEDICATED_VM_HOST_DELETE | USE + `CreateDedicatedVmHost`, `DeleteDedicatedVmHost`, `ChangeDedicatedVmHostCompartment` | USE + none |

#### work-requests

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | WORKREQUEST_INSPECT | `ListWorkRequests` | none |
| read / use / manage | no extra | no extra | none |

### For `volume-family` Resource Types

#### volumes

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VOLUME_INSPECT | `ListVolumes`, `GetVolume` | `ListVolumeBackups`, `GetVolumeBackup` (also need `inspect volume-backups`); `UpdateVolumeBackup` (also needs `read volume-backups`); `DeleteVolumeBackup` (also needs `manage volume-backups`); `CreateInstanceConfiguration` (with the `FromInstanceDetails` subtype; also needs `read instances`, `inspect vnics`, `inspect vnic-attachments`, `inspect volume-attachments`) |
| read | no extra | no extra | no extra |
| use | READ + VOLUME_UPDATE, VOLUME_WRITE | no extra | READ + `AttachVolume`, `DetachVolume` (both also need `manage volume-attachments`, `use instances`); `CreateVolumeBackup` (also needs `manage volume-backups`) |
| manage | USE + VOLUME_CREATE, VOLUME_DELETE, VOLUME_MOVE | USE + `CreateVolume`, `DeleteVolume`, `ChangeVolumeCompartment` (when moving between compartments, `move volume` is needed on both source and destination) | USE + creating a volume _from a backup_ also needs `read volume-backups`; creating a volume _encrypted with a Vault key_ also needs `use key-delegate` (caller) and `read keys` (service principal). |

#### volume-attachments

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VOLUME_ATTACHMENT_INSPECT | `ListVolumeAttachments` | `GetVolumeAttachment` (also needs `inspect volumes` and `inspect instances`). **Note:** CHAP secret (if any) is NOT included with `inspect`. `CreateInstanceConfiguration` (with the `FromInstanceDetails` subtype; also needs `read instances`, `inspect vnics`, `inspect vnic-attachments`, `inspect volumes`) |
| read | INSPECT + VOLUME_ATTACHMENT_READ | no extra | Same as inspect, but `GetVolumeAttachment` now includes the CHAP secret if it exists. |
| use | READ + VOLUME_ATTACHMENT_UPDATE | no extra | no extra |
| manage | USE + VOLUME_ATTACHMENT_CREATE, VOLUME_ATTACHMENT_DELETE | no extra | USE + `AttachVolume`, `DetachVolume` (both also need `use volumes` and `use instances`) |

#### volume-backups

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VOLUME_BACKUP_INSPECT | none | `ListVolumeBackups`, `GetVolumeBackup` (both also need `inspect volumes`) |
| read | INSPECT + VOLUME_BACKUP_READ | none | INSPECT + `CreateVolume` when creating a volume from a backup (also needs `manage volumes`) |
| use | READ + VOLUME_BACKUP_COPY, VOLUME_BACKUP_UPDATE | none | READ + `UpdateVolumeBackup` (also needs `inspect volumes`); `CopyVolumeBackup` (also needs `create volume backups` in destination region) |
| manage | USE + VOLUME_BACKUP_CREATE, VOLUME_BACKUP_DELETE, VOLUME_BACKUP_MOVE | `ChangeVolumeBackupCompartment` (when moving between compartments, `move volume backup` is needed on both source and destination) | USE + `CreateVolumeBackup` (also needs `use volumes`); `DeleteVolumeBackup` (also needs `inspect volumes`) |

#### boot-volume-backups

Mirrors `volume-backups`, but with `BOOT_VOLUME_BACKUP_*` permissions and the `CreateBootVolume*` / `UpdateBootVolumeBackup` / `CopyBootVolumeBackup` / `DeleteBootVolumeBackup` APIs.

#### backup-policies

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | BACKUP_POLICY_INSPECT | `ListVolumeBackupPolicies`, `GetVolumeBackupPolicy` | none |
| read | no extra | no extra | no extra |
| use | READ + BACKUP_POLICIES_UPDATE | READ + `UpdateVolumeBackupPolicy` | none |
| manage | USE + BACKUP_POLICIES_CREATE, BACKUP_POLICIES_DELETE | USE + `CreateVolumeBackupPolicy`, `DeleteVolumeBackupPolicy` | none |

#### backup-policy-assignments

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | BACKUP_POLICY_ASSIGNMENT_INSPECT | `GetVolumeBackupPolicyAssignment` | `GetVolumeBackupPolicyAssetAssignment` (also needs `inspect volumes`) |
| read / use | no extra | no extra | no extra |
| manage | USE + BACKUP_POLICY_ASSIGNMENT_CREATE, BACKUP_POLICY_ASSIGNMENT_DELETE | USE + `CreateVolumeBackupPolicyAssignment`, `DeleteVolumeBackupPolicyAssignment` | none |

#### volume-groups

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VOLUME_GROUP_INSPECT | `ListVolumeGroups`, `GetVolumeGroup` | no extra |
| read / use | no extra | no extra | no extra |
| manage | USE + VOLUME_GROUP_UPDATE, VOLUME_GROUP_CREATE, VOLUME_GROUP_DELETE, VOLUME_GROUP_MOVE | USE + `DeleteVolumeGroup` | USE + `UpdateVolumeGroup` (also needs `inspect volume` for the volumes in the request); `CreateVolumeGroup` (from a _list of volumes_, also needs `inspect volume`; from another _volume group_, also needs `inspect volume group` on source, `create volume group` on destination, `write volume` on source, `create volume` + `write volume` on destination; from a _volume group backup_, also needs `inspect volume group backup` on source, `create volume group` on destination, `read volume backup`/`read boot volume backup` on source, `create volume` + `write volume` on destination); `ChangeVolumeGroupCompartment` (also needs `move volume` or `move boot volume`; `move volume group` and `move volume` both needed on source and destination) |

#### volume-group-backups

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | VOLUME_GROUP_BACKUP_INSPECT | `ListVolumeGroupBackups`, `GetVolumeGroupBackup` | no extra |
| read / use | no extra | no extra | no extra |
| manage | USE + VOLUME_GROUP_BACKUP_CREATE, VOLUME_GROUP_BACKUP_DELETE, VOLUME_GROUP_BACKUP_UPDATE, VOLUME_GROUP_BACKUP_MOVE | `CreateVolumeGroupBackup` (also needs `VOLUME_GROUP_INSPECT`, `VOLUME_WRITE`, `VOLUME_BACKUP_CREATE` / `BOOT_VOLUME_BACKUP_CREATE`); `DeleteVolumeGroupBackup` (also needs `VOLUME_BACKUP_DELETE` / `BOOT_VOLUME_BACKUP_DELETE`); `UpdateVolumeGroupBackup`; `ChangeVolumeGroupBackupCompartment` (also needs `VOLUME_BACKUP_MOVE` / `BOOT_VOLUME_BACKUP_MOVE`) | |

## Permissions Required for Each API Operation

### Core Services API Operations

| API Operation | Permissions Required |
|---|---|
| `CreateVolumeBackupPolicy` | BACKUP_POLICIES_CREATE |
| `DeleteVolumeBackupPolicy` | BACKUP_POLICIES_DELETE |
| `GetVolumeBackupPolicy` | BACKUP_POLICIES_INSPECT |
| `ListVolumeBackupPolicies` | BACKUP_POLICIES_INSPECT |
| `CreateVolumeBackupPolicyAssignment` | BACKUP_POLICY_ASSIGNMENT_CREATE |
| `DeleteVolumeBackupPolicyAssignment` | BACKUP_POLICY_ASSIGNMENT_DELETE |
| `GetVolumeBackupPolicyAssetAssignment` | BACKUP_POLICY_ASSIGNMENT_INSPECT and VOLUME_INSPECT |
| `GetVolumeBackupPolicyAssignment` | BACKUP_POLICY_ASSIGNMENT_INSPECT |
| `CreateComputeCapacityReport` | COMPUTE_CAPACITY_REPORT_CREATE |
| `ListClusterNetworks` | CLUSTER_NETWORK_INSPECT and INSTANCE_POOL_INSPECT |
| `ListClusterNetworkInstances` | CLUSTER_NETWORK_READ and INSTANCE_POOL_READ |
| `GetClusterNetwork` | CLUSTER_NETWORK_READ and INSTANCE_POOL_READ |
| `UpdateClusterNetwork` | CLUSTER_NETWORK_UPDATE |
| `CreateClusterNetwork` | CLUSTER_NETWORK_CREATE and INSTANCE_POOL_CREATE |
| `ChangeClusterNetworkCompartment` | CLUSTER_NETWORK_MOVE |
| `TerminateClusterNetwork` | CLUSTER_NETWORK_DELETE and INSTANCE_POOL_DELETE |
| `ListConsoleHistories` | CONSOLE_HISTORY_READ and INSTANCE_INSPECT |
| `CreateComputeCluster` | COMPUTE_CLUSTER_CREATE |
| `ListComputeClusters` | COMPUTE_CLUSTER_INSPECT |
| `GetComputeCluster` | COMPUTE_CLUSTER_READ |
| `UpdateComputeCluster` | COMPUTE_CLUSTER_UPDATE |
| `ChangeComputeClusterCompartment` | COMPUTE_CLUSTER_MOVE |
| `DeleteComputeCluster` | COMPUTE_CLUSTER_DELETE |
| `GetConsoleHistory` | CONSOLE_HISTORY_READ and INSTANCE_INSPECT |
| `ShowConsoleHistoryData` | CONSOLE_HISTORY_READ and INSTANCE_READ and INSTANCE_IMAGE_READ |
| `CaptureConsoleHistory` | CONSOLE_HISTORY_CREATE and INSTANCE_READ and INSTANCE_IMAGE_READ |
| `DeleteConsoleHistory` | CONSOLE_HISTORY_DELETE |
| `ListCpes` | CPE_READ |
| `GetCpe` | CPE_READ |
| `UpdateCpe` | CPE_UPDATE |
| `CreateCpe` | CPE_CREATE |
| `DeleteCpe` | CPE_DELETE |
| `ChangeCpeCompartment` | CPE_RESOURCE_MOVE |
| `UpdateTunnelCpeDeviceConfig` | IPSEC_CONNECTION_UPDATE |
| `GetTunnelCpeDeviceConfig` | IPSEC_CONNECTION_READ |
| `ListCrossConnects` | CROSS_CONNECT_READ |
| `GetCrossConnect` | CROSS_CONNECT_READ |
| `UpdateCrossConnect` | CROSS_CONNECT_UPDATE |
| `CreateCrossConnect` | CROSS_CONNECT_CREATE (if not creating inside a cross-connect group; if creating in a group, also CROSS_CONNECT_ATTACH) |
| `DeleteCrossConnect` | CROSS_CONNECT_DELETE (if not in a cross-connect group; if in a group, also CROSS_CONNECT_DETACH) |
| `ChangeCrossConnectCompartment` | CROSS_CONNECT_RESOURCE_MOVE |
| `ListCrossConnectGroups` | CROSS_CONNECT_GROUP_READ |
| `GetCrossConnectGroup` | CROSS_CONNECT_GROUP_READ |
| `UpdateCrossConnectGroup` | CROSS_CONNECT_GROUP_UPDATE |
| `CreateCrossConnectGroup` | CROSS_CONNECT_GROUP_CREATE |
| `DeleteCrossConnectGroup` | CROSS_CONNECT_GROUP_DELETE |
| `ChangeCrossConnectGroupCompartment` | CROSS_CONNECT_GROUP_RESOURCE_MOVE |
| `ListDhcpOptions` | DHCP_READ |
| `GetDhcpOptions` | DHCP_READ |
| `UpdateDhcpOptions` | DHCP_UPDATE |
| `CreateDhcpOptions` | DHCP_CREATE and VCN_ATTACH |
| `DeleteDhcpOptions` | DHCP_DELETE and VCN_DETACH |
| `ChangeDhcpOptionsCompartment` | DHCP_MOVE |
| `ListDrgs` | DRG_READ |
| `GetDrg` | DRG_READ |
| `UpdateDrg` | DRG_UPDATE |
| `CreateDrg` | DRG_CREATE |
| `DeleteDrg` | DRG_DELETE |
| `ChangeDrgCompartment` | DRG_MOVE |
| `ListDrgAttachments` | DRG_ATTACHMENT_READ |
| `GetDrgAttachment` | DRG_ATTACHMENT_READ |
| `UpdateDrgAttachment` | DRG_ATTACHMENT_UPDATE (plus ROUTE_TABLE_ATTACH if associating a route table) |
| `CreateDrgAttachment` | DRG_ATTACH and VCN_ATTACH (plus ROUTE_TABLE_ATTACH if associating a route table) |
| `DeleteDrgAttachment` | DRG_DETACH or VCN_DETACH |
| `CreateDrgRouteTable` / `DeleteDrgRouteTable` / `GetDrgRouteTable` / `ListDrgRouteTables` / `UpdateDrgRouteTable` | DRG_ROUTE_TABLE_{CREATE,DELETE,READ,READ,UPDATE} |
| `UpdateDrgRouteRules` / `RemoveDrgRouteRules` / `AddDrgRouteRules` | DRG_ROUTE_RULE_UPDATE |
| `ListDrgRouteRules` | DRG_ROUTE_RULE_READ |
| `Get/List/Create/Delete/UpdateDrgRouteDistribution` | DRG_ROUTE_DISTRIBUTION_{READ,READ,CREATE,DELETE,UPDATE} |
| `Update/Remove/AddDrgRouteDistributionStatements` | DRG_ROUTE_DISTRIBUTION_STATEMENT_UPDATE |
| `ListDrgRouteDistributionStatements` | DRG_ROUTE_DISTRIBUTION_STATEMENT_READ |
| `Remove{Export,Import}DrgRouteDistribution` | DRG_ROUTE_DISTRIBUTION_ASSIGN |
| `CreateInstanceConsoleConnection` | INSTANCE_CONSOLE_CONNECTION_CREATE and INSTANCE_READ |
| `DeleteInstanceConsoleConnection` | INSTANCE_CONSOLE_CONNECTION_DELETE |
| `GetInstanceConsoleConnection` | INSTANCE_CONSOLE_CONNECTION_READ and INSTANCE_READ |
| `UpdateInstanceConsoleConnection` | INSTANCE_CONSOLE_CONNECTION_CREATE and INSTANCE_CONSOLE_CONNECTION_DELETE |
| `ListInstanceConsoleConnections` | INSTANCE_CONSOLE_CONNECTION_INSPECT and INSTANCE_INSPECT and INSTANCE_READ |
| `ListImages` | INSTANCE_IMAGE_INSPECT |
| `GetImage` | INSTANCE_IMAGE_INSPECT |
| `UpdateImage` | INSTANCE_IMAGE_UPDATE |
| `CreateImage` | INSTANCE_IMAGE_CREATE and INSTANCE_CREATE_IMAGE |
| `ChangeImageCompartment` | INSTANCE_IMAGE_MOVE |
| `DeleteImage` | INSTANCE_IMAGE_DELETE |
| `LaunchInstance` | INSTANCE_CREATE, INSTANCE_IMAGE_READ, VNIC_CREATE, VNIC_ATTACH, SUBNET_ATTACH. If placing the instance in an NSG on creation, also NETWORK_SECURITY_GROUP_UPDATE_MEMBERS, VNIC_ASSOCIATE_NETWORK_SECURITY_GROUP. If in a compute cluster, also COMPUTE_CLUSTER_LAUNCH_INSTANCE. |
| `ListInstances` | INSTANCE_READ (and COMPUTE_CLUSTER_READ if listing in a compute cluster) |
| `ListInstanceDevices` | INSTANCE_READ |
| `GetInstance` | INSTANCE_READ |
| `GetInstanceMaintenanceReboot` | INSTANCE_READ |
| `UpdateInstance` | INSTANCE_UPDATE |
| `InstanceAction` | INSTANCE_POWER_ACTIONS |
| `ChangeInstanceCompartment` | INSTANCE_MOVE |
| `TerminateInstance` | INSTANCE_DELETE, VNIC_DELETE, SUBNET_DETACH. If volumes are attached, also VOLUME_ATTACHMENT_DELETE, VOLUME_WRITE, INSTANCE_DETACH_VOLUME. |
| `ListInstanceConfigurations` | INSTANCE_CONFIGURATION_INSPECT |
| `GetInstanceConfiguration` | INSTANCE_CONFIGURATION_READ |
| `LaunchInstanceConfiguration` | INSTANCE_CONFIGURATION_LAUNCH |
| `UpdateInstanceConfiguration` | INSTANCE_CONFIGURATION_UPDATE |
| `CreateInstanceConfiguration` | INSTANCE_CONFIGURATION_CREATE (with `CreateInstanceConfigurationDetails`); or INSTANCE_READ + VNIC_READ + VNIC_ATTACHMENT_READ + VOLUME_INSPECT + VOLUME_ATTACHMENT_INSPECT (with `CreateInstanceConfigurationFromInstanceDetails`) |
| `ChangeInstanceConfigurationCompartment` | INSTANCE_CONFIGURATION_MOVE |
| `DeleteInstanceConfiguration` | INSTANCE_CONFIGURATION_DELETE |
| `CreateInstancePool` | INSTANCE_POOL_CREATE and INSTANCE_CREATE and IMAGE_READ and VNIC_CREATE and SUBNET_ATTACH |
| `ListInstancePools` | INSTANCE_POOL_INSPECT |
| `ListInstancePoolInstances` | INSTANCE_POOL_READ |
| `GetInstancePool` | INSTANCE_POOL_READ |
| `UpdateInstancePool` | INSTANCE_POOL_UPDATE |
| `AttachInstancePoolInstance` | INSTANCE_POOL_INSTANCE_ATTACH |
| `DetachInstancePoolInstance` | INSTANCE_POOL_INSTANCE_DETACH |
| `Start/Stop/Reset/SoftresetInstancePool` | INSTANCE_POOL_POWER_ACTIONS |
| `ChangeInstancePoolCompartment` | INSTANCE_POOL_MOVE |
| `TerminateInstancePool` | INSTANCE_POOL_DELETE, INSTANCE_DELETE, VNIC_DELETE, SUBNET_DETACH, VOLUME_ATTACHMENT_DELETE, VOLUME_WRITE |
| `ListInternetGateways` / `GetInternetGateway` | INTERNET_GATEWAY_READ |
| `UpdateInternetGateway` | INTERNET_GATEWAY_UPDATE |
| `CreateInternetGateway` | INTERNET_GATEWAY_CREATE and VCN_ATTACH |
| `DeleteInternetGateway` | INTERNET_GATEWAY_DELETE and VCN_DETACH |
| `ChangeInternetGatewayCompartment` | INTERNET_GATEWAY_MOVE |
| `ListIPSecConnections` / `GetIPSecConnection` | IPSEC_CONNECTION_READ |
| `UpdateIpSecConnection` | IPSEC_CONNECTION_UPDATE |
| `CreateIPSecConnection` | DRG_ATTACH, CPE_ATTACH, IPSEC_CONNECTION_CREATE (plus DRG_ROUTE_TABLE_{ATTACH,CREATE,UPDATE} and DRG_ROUTE_DISTRIBUTION_{CREATE,UPDATE,ASSIGN}, DRG_ROUTE_DISTRIBUTION_STATEMENT_UPDATE if over FastConnect) |
| `DeleteIPSecConnection` | DRG_DETACH, CPE_DETACH, IPSEC_CONNECTION_DELETE (plus related DRG_ROUTE_TABLE_* if over FastConnect) |
| `ListIpv6s` | IPV6_READ (+ SUBNET_READ / VNIC_READ if listing by subnet or VNIC) |
| `GetIpv6` | IPV6_READ |
| `UpdateIpv6` / `BulkUpdateIpv6s` | IPV6_UPDATE (+ VNIC_UNASSIGN + VNIC_ASSIGN if moving IPv6 to a different VNIC) |
| `CreateIpv6` / `BulkCreateIpv6s` | IPV6_CREATE, SUBNET_ATTACH, VNIC_ASSIGN |
| `DeleteIpv6` / `BulkDeleteIpv6s` | IPV6_DELETE, SUBNET_DETACH, VNIC_UNASSIGN |
| `Get/Update/Create/DeleteLocalPeeringGateway` / `ConnectLocalPeeringGateways` / `ChangeLocalPeeringGatewayCompartment` | LOCAL_PEERING_GATEWAY_{READ,UPDATE,CREATE,DELETE,CONNECT_FROM+CONNECT_TO,MOVE} (plus VCN_ATTACH/DETACH, ROUTE_TABLE_ATTACH where associating route tables) |
| `List/Get/Update/Create/DeleteNatGateway` / `ChangeNatGatewayCompartment` | NAT_GATEWAY_{READ,READ,UPDATE,CREATE+VCN_READ+VCN_ATTACH,DELETE+VCN_READ+VCN_DETACH,MOVE} |
| `List/Get/UpdateNetworkSecurityGroup` | NETWORK_SECURITY_GROUP_{READ,READ,UPDATE} |
| `CreateNetworkSecurityGroup` | NETWORK_SECURITY_GROUP_CREATE and VCN_ATTACH |
| `DeleteNetworkSecurityGroup` | NETWORK_SECURITY_GROUP_DELETE and VCN_DETACH |
| `ChangeNetworkSecurityGroupCompartment` | NETWORK_SECURITY_GROUP_MOVE |
| `ListNetworkSecurityGroupSecurityRules` | NETWORK_SECURITY_GROUP_LIST_SECURITY_RULES |
| `Update/Add/RemoveNetworkSecurityGroupSecurityRules` | NETWORK_SECURITY_GROUP_UPDATE_SECURITY_RULES (+ NETWORK_SECURITY_GROUP_INSPECT if the rule specifies an NSG as source/destination) |
| `ListPrivateIps` / `GetPrivateIp` | PRIVATE_IP_READ |
| `UpdatePrivateIp` / `BulkUpdatePrivateIps` | PRIVATE_IP_UPDATE, VNIC_ASSIGN, VNIC_UNASSIGN |
| `CreatePrivateIp` / `BulkCreatePrivateIps` | PRIVATE_IP_CREATE, PRIVATE_IP_ASSIGN, VNIC_ASSIGN, SUBNET_ATTACH |
| `DeletePrivateIp` / `BulkDeletePrivateIps` | PRIVATE_IP_DELETE, PRIVATE_IP_UNASSIGN, VNIC_UNASSIGN, SUBNET_DETACH |
| `ListRemotePeeringConnections` / `GetRemotePeeringConnection` | REMOTE_PEERING_CONNECTION_READ |
| `UpdateRemotePeeringConnection` | REMOTE_PEERING_CONNECTION_UPDATE |
| `CreateRemotePeeringConnection` | REMOTE_PEERING_CONNECTION_CREATE and DRG_ATTACH |
| `DeleteRemotePeeringConnection` | REMOTE_PEERING_CONNECTION_DELETE and DRG_DETACH |
| `ChangeRemotePeeringConnectionCompartment` | REMOTE_PEERING_CONNECTION_RESOURCE_MOVE |
| `ConnectRemotePeeringConnections` | REMOTE_PEERING_CONNECTION_CONNECT_FROM and REMOTE_PEERING_CONNECTION_CONNECT_TO |
| `ListPublicIps` / `GetPublicIp` / `GetPublicIpByPrivateIpId` / `GetPublicIpByIpAddress` | ephemeral: PRIVATE_IP_READ; reserved: PUBLIC_IP_READ |
| `UpdatePublicIP` | ephemeral: PRIVATE_IP_UPDATE; reserved: PUBLIC_IP_UPDATE + PRIVATE_IP_ASSIGN_PUBLIC_IP + PUBLIC_IP_ASSIGN_PRIVATE_IP + PRIVATE_IP_UNASSIGN_PUBLIC_IP + PUBLIC_IP_UNASSIGN_PRIVATE_IP |
| `CreatePublicIp` | ephemeral: PRIVATE_IP_ASSIGN_PUBLIC_IP; reserved: PUBLIC_IP_CREATE + PUBLIC_IP_ASSIGN_PRIVATE_IP + PRIVATE_IP_ASSIGN_PUBLIC_IP |
| `DeletePublicIp` | ephemeral: PRIVATE_IP_UNASSIGN_PUBLIC_IP; reserved: PUBLIC_IP_DELETE + PUBLIC_IP_UNASSIGN_PRIVATE_IP + PRIVATE_IP_UNASSIGN_PUBLIC_IP |
| `ChangePublicIpCompartment` | PUBLIC_IP_MOVE (reserved only) |
| `ListRouteTables` / `GetRouteTable` | ROUTE_TABLE_READ |
| `UpdateRouteTable` | ROUTE_TABLE_UPDATE (+ INTERNET_GATEWAY_{ATTACH,DETACH}, DRG_{ATTACH,DETACH}, PRIVATE_IP_ROUTE_TABLE_{ATTACH,DETACH}, LOCAL_PEERING_GATEWAY_{ATTACH,DETACH}, NAT_GATEWAY_{ATTACH,DETACH}, SERVICE_GATEWAY_{ATTACH,DETACH} when creating/deleting route rules with those targets) |
| `CreateRouteTable` | ROUTE_TABLE_CREATE and VCN_ATTACH (+ target-specific *_ATTACH for each rule type in the table) |
| `DeleteRouteTable` | ROUTE_TABLE_DELETE and VCN_DETACH (+ target-specific *_DETACH for each rule type) |
| `ChangeRouteTableCompartment` | ROUTE_TABLE_MOVE |
| `ListSecurityLists` / `GetSecurityList` | SECURITY_LIST_READ |
| `UpdateSecurityList` | SECURITY_LIST_UPDATE |
| `ChangeSecurityListCompartment` | SECURITY_LIST_MOVE |
| `CreateSecurityList` | SECURITY_LIST_CREATE and VCN_ATTACH |
| `DeleteSecurityList` | SECURITY_LIST_DELETE and VCN_DETACH |
| `ListServiceGateways` / `GetServiceGateway` | SERVICE_GATEWAY_READ |
| `UpdateServiceGateway` | SERVICE_GATEWAY_UPDATE (+ ROUTE_TABLE_ATTACH if associating a route table on update) |
| `ChangeServiceGatewayCompartment` | SERVICE_GATEWAY_MOVE |
| `CreateServiceGateway` | SERVICE_GATEWAY_CREATE and VCN_READ and VCN_ATTACH (+ ROUTE_TABLE_ATTACH if associating a route table on create) |
| `DeleteServiceGateway` | SERVICE_GATEWAY_DELETE and VCN_READ and VCN_DETACH |
| `AttachServiceId` | SERVICE_GATEWAY_ADD_SERVICE |
| `DetachServiceId` | SERVICE_GATEWAY_DELETE_SERVICE |
| `ListShapes` | INSTANCE_INSPECT |
| `ListSubnets` / `GetSubnet` | SUBNET_READ |
| `UpdateSubnet` | SUBNET_UPDATE (+ ROUTE_TABLE_{ATTACH,DETACH}, SECURITY_LIST_{ATTACH,DETACH}, DHCP_{ATTACH,DETACH} if changing those associations) |
| `CreateSubnet` | SUBNET_CREATE, VCN_ATTACH, ROUTE_TABLE_ATTACH, SECURITY_LIST_ATTACH, DHCP_ATTACH |
| `DeleteSubnet` | SUBNET_DELETE, VCN_DETACH, ROUTE_TABLE_DETACH, SECURITY_LIST_DETACH, DHCP_DETACH |
| `ChangeSubnetCompartment` | SUBNET_MOVE |
| `ListVcns` / `GetVcn` | VCN_READ |
| `UpdateVcn` / `AddVcnCidr` / `ModifyVcnCidr` / `RemoveVcnCidr` | VCN_UPDATE |
| `CreateVcn` | VCN_CREATE |
| `DeleteVcn` | VCN_DELETE |
| `ChangeVcnCompartment` | VCN_MOVE |
| `ListVirtualCircuits` / `GetVirtualCircuit` | VIRTUAL_CIRCUIT_READ |
| `UpdateVirtualCircuit` | VIRTUAL_CIRCUIT_UPDATE and DRG_ATTACH and DRG_DETACH (+ CROSS_CONNECT_{DETACH,ATTACH} if changing cross-connect) |
| `CreateVirtualCircuit` | VIRTUAL_CIRCUIT_CREATE and DRG_ATTACH (+ CROSS_CONNECT_ATTACH if mapping to a specific cross-connect) |
| `DeleteVirtualCircuit` | VIRTUAL_CIRCUIT_DELETE and DRG_DETACH (+ CROSS_CONNECT_DETACH if currently using a cross-connect) |
| `ChangeVirtualCircuitCompartment` | VIRTUAL_CIRCUIT_RESOURCE_MOVE |
| `ListVlans` / `GetVlan` | VLAN_READ |
| `CreateVlan` | VLAN_CREATE, VCN_ATTACH, ROUTE_TABLE_ATTACH, SECURITY_LIST_ATTACH, VLAN_ASSOCIATE_NETWORK_SECURITY_GROUP |
| `UpdateVlan` | VLAN_UPDATE |
| `DeleteVlan` | VLAN_DELETE, VCN_DETACH, ROUTE_TABLE_DETACH, SECURITY_LIST_DETACH, VLAN_DISASSOCIATE_NETWORK_SECURITY_GROUP |
| `ChangeVlanCompartment` | VLAN_MOVE |
| `GetVnic` | VNIC_READ |
| `AttachVnic` | INSTANCE_ATTACH_SECONDARY_VNIC, VNIC_ATTACH, VNIC_CREATE, SUBNET_ATTACH (+ NETWORK_SECURITY_GROUP_UPDATE_MEMBERS, VNIC_ASSOCIATE_NETWORK_SECURITY_GROUP if placing the VNIC in an NSG) |
| `DetachVnic` | INSTANCE_DETACH_SECONDARY_VNIC, VNIC_DETACH, VNIC_DELETE, SUBNET_DETACH |
| `UpdateVnic` | VNIC_UPDATE (+ NETWORK_SECURITY_GROUP_UPDATE_MEMBERS, VNIC_ASSOCIATE_NETWORK_SECURITY_GROUP if adding/removing NSGs) |
| `ListVnicAttachments` | VNIC_ATTACHMENT_READ and INSTANCE_INSPECT |
| `GetVnicAttachment` | VNIC_ATTACHMENT_READ |
| `ListVolumes` / `GetVolume` | VOLUME_INSPECT |
| `UpdateVolume` | VOLUME_UPDATE |
| `CreateVolume` | VOLUME_CREATE (+ VOLUME_BACKUP_READ if creating from a backup) |
| `DeleteVolume` | VOLUME_DELETE |
| `ChangeVolumeCompartment` | VOLUME_MOVE |
| `ListVolumeAttachments` | VOLUME_ATTACHMENT_INSPECT and VOLUME_INSPECT and INSTANCE_INSPECT |
| `GetVolumeAttachment` | VOLUME_ATTACHMENT_INSPECT and INSTANCE_INSPECT (VOLUME_ATTACHMENT_READ required to also get the CHAP secret) |
| `AttachVolume` | VOLUME_ATTACHMENT_CREATE, VOLUME_WRITE, INSTANCE_ATTACH_VOLUME |
| `DetachVolume` | VOLUME_ATTACHMENT_DELETE, VOLUME_WRITE, INSTANCE_DETACH_VOLUME |
| `ListVolumeBackups` | VOLUME_BACKUP_INSPECT and VOLUME_INSPECT |
| `GetVolumeBackup` | VOLUME_BACKUP_INSPECT and VOLUME_INSPECT |
| `UpdateVolumeBackup` | VOLUME_BACKUP_UPDATE and VOLUME_INSPECT |
| `CreateVolumeBackup` | VOLUME_BACKUP_CREATE and VOLUME_WRITE |
| `DeleteVolumeBackup` | VOLUME_BACKUP_DELETE and VOLUME_INSPECT |
| `ChangeVolumeBackupCompartment` | VOLUME_BACKUP_MOVE |
| `GetBootVolume` / `ListBootVolumes` | VOLUME_INSPECT |
| `UpdateBootVolume` | VOLUME_UPDATE |
| `DeleteBootVolume` | VOLUME_DELETE |
| `ChangeBootVolumeCompartment` | BOOT_VOLUME_MOVE |
| `CreateBootVolumeBackup` | BOOT_VOLUME_BACKUP_CREATE, VOLUME_WRITE |
| `ListBootVolumeBackups` / `GetBootVolumeBackup` | BOOT_VOLUME_BACKUP_INSPECT, VOLUME_INSPECT |
| `UpdateBootVolumeBackup` | BOOT_VOLUME_BACKUP_UPDATE, VOLUME_INSPECT |
| `DeleteBootVolumeBackup` | BOOT_VOLUME_BACKUP_DELETE, VOLUME_INSPECT |
| `ChangeBootVolumeBackupCompartment` | BOOT_VOLUME_BACKUP_MOVE |
| `CreateVolumeGroup` | VOLUME_GROUP_CREATE + VOLUME_INSPECT (from list of volumes); or VOLUME_GROUP_CREATE + VOLUME_GROUP_INSPECT + VOLUME_CREATE + VOLUME_WRITE (cloning); or VOLUME_GROUP_CREATE + VOLUME_GROUP_BACKUP_INSPECT + VOLUME_BACKUP_READ/BOOT_VOLUME_BACKUP_READ + VOLUME_CREATE + VOLUME_WRITE (restoring from backup) |
| `DeleteVolumeGroup` | VOLUME_GROUP_DELETE |
| `GetVolumeGroup` / `ListVolumeGroups` | VOLUME_GROUP_INSPECT |
| `UpdateVolumeGroup` | VOLUME_GROUP_UPDATE, VOLUME_INSPECT |
| `ChangeVolumeGroupCompartment` | VOLUME_GROUP_MOVE, VOLUME_MOVE/BOOT_VOLUME_MOVE |
| `CreateVolumeGroupBackup` | VOLUME_GROUP_BACKUP_CREATE, VOLUME_GROUP_INSPECT, VOLUME_WRITE, VOLUME_BACKUP_CREATE/BOOT_VOLUME_BACKUP_CREATE |
| `DeleteVolumeGroupBackup` | VOLUME_GROUP_BACKUP_DELETE, VOLUME_BACKUP_DELETE/BOOT_VOLUME_BACKUP_DELETE |
| `GetVolumeGroupBackup` / `ListVolumeGroupBackups` | VOLUME_GROUP_BACKUP_INSPECT |
| `UpdateVolumeGroupBackup` | VOLUME_GROUP_BACKUP_UPDATE |
| `ChangeVolumeGroupBackupCompartment` | VOLUME_GROUP_BACKUP_MOVE, VOLUME_BACKUP_MOVE/BOOT_VOLUME_BACKUP_MOVE |
| `ListIpInventory` / `GetVcnOverlap` / `GetSubnetIpInventory` / `GetSubnetCidrUtilization` | IPAM_READ |

### Dedicated Virtual Machine Host API Operations

| API Operation | Permissions Required |
|---|---|
| `CreateDedicatedVmHost` | DEDICATED_VM_HOST_CREATE |
| `ChangeDedicatedVmHostCompartment` | DEDICATED_VM_HOST_MOVE |
| `DeleteDedicatedVmHost` | DEDICATED_VM_HOST_DELETE |
| `GetDedicatedVmHost` | DEDICATED_VM_HOST_READ |
| `ListDedicatedVmHosts` | DEDICATED_VM_HOST_INSPECT |
| `ListDedicatedVmHostInstances` | DEDICATED_VM_HOST_READ |
| `ListDedicatedVmHostInstanceShapes` / `ListDedicatedVmHostShapes` | None |
| `LaunchInstance` (on a DVH) | DEDICATED_VM_HOST_LAUNCH_INSTANCE (in DVH compartment) + INSTANCE_CREATE (in instance's compartment) |
| `UpdateDedicatedVmHost` | AUTO_SCALING_CONFIGURATION_CREATE and INSTANCE_POOL_UPDATE |

### Autoscaling API Operations

| API Operation | Permissions Required |
|---|---|
| `ListAutoScalingConfigurations` | AUTO_SCALING_CONFIGURATION_INSPECT |
| `GetAutoScalingConfiguration` | AUTO_SCALING_CONFIGURATION_READ |
| `UpdateAutoScalingConfiguration` | AUTO_SCALING_CONFIGURATION_UPDATE and INSTANCE_POOL_UPDATE |
| `CreateAutoScalingConfiguration` | AUTO_SCALING_CONFIGURATION_CREATE and INSTANCE_POOL_UPDATE |
| `ChangeAutoScalingConfigurationCompartment` | AUTO_SCALING_CONFIGURATION_MOVE |
| `DeleteAutoScalingConfiguration` | AUTO_SCALING_CONFIGURATION_DELETE and INSTANCE_POOL_UPDATE |
| `ListAutoScalingPolicies` / `GetAutoScalingPolicy` | AUTO_SCALING_CONFIGURATION_READ |
| `UpdateAutoScalingPolicy` | AUTO_SCALING_CONFIGURATION_UPDATE and INSTANCE_POOL_UPDATE |
| `CreateAutoScalingPolicy` | AUTO_SCALING_CONFIGURATION_CREATE and INSTANCE_POOL_UPDATE |
| `DeleteAutoScalingPolicy` | AUTO_SCALING_CONFIGURATION_DELETE and INSTANCE_POOL_UPDATE |

### Compute Capacity Reservation API Operations

| API Operation | Permissions Required |
|---|---|
| `ListComputeCapacityReservations` | CAPACITY_RESERVATION_INSPECT |
| `GetComputeCapacityReservation` | CAPACITY_RESERVATION_READ |
| `UpdateComputeCapacityReservation` | CAPACITY_RESERVATION_UPDATE |
| `CreateComputeCapacityReservation` | CAPACITY_RESERVATION_CREATE |
| `ChangeComputeCapacityReservationCompartment` | CAPACITY_RESERVATION_MOVE |
| `DeleteComputeCapacityReservation` | CAPACITY_RESERVATION_DELETE |
| `ListComputeCapacityReservationInstances` | CAPACITY_RESERVATION_READ |
| `ListComputeCapacityReservationInstanceShapes` | CAPACITY_RESERVATION_INSPECT |

### Oracle Cloud Agent API Operations

| API Operation | Permissions Required |
|---|---|
| `CreateInstanceAgentCommand` | INSTANCE_AGENT_COMMAND_CREATE |
| `GetInstanceAgentCommand` | INSTANCE_AGENT_COMMAND_READ |
| `GetInstanceAgentCommandExecution` | INSTANCE_AGENT_COMMAND_EXECUTION_INSPECT |
| `ListInstanceAgentCommands` | INSTANCE_AGENT_COMMAND_INSPECT |
| `ListInstanceAgentCommandExecutions` | INSTANCE_AGENT_COMMAND_EXECUTION_INSPECT |
| `CancelInstanceAgentCommand` | INSTANCE_AGENT_COMMAND_DELETE |
| `GetInstanceAgentPlugin` | INSTANCE_AGENT_PLUGIN_READ |
| `ListInstanceAgentPlugins` / `ListInstanceagentAvailablePlugins` | INSTANCE_AGENT_PLUGIN_INSPECT |

### Work Requests API Operations

| API Operation | Permissions Required |
|---|---|
| `ListWorkRequests` | WORKREQUEST_INSPECT |
| `GetWorkRequests` / `ListWorkRequestLogs` / `ListWorkRequestErrors` | Inherits the permissions of the operation that spawned the work request. Generally, `<RESOURCE>_CREATE` for the associated resource. |
