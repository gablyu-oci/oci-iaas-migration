---
title: "Managing Network Sources"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingnetworksources.htm"
fetched: "20260306T012113Z"
---

To restrict access to requests made from a set of IP addresses, do the following:

1.  Create a network source that specifies the allowed IP addresses.
2.  Write a policy that uses the network source variable in a condition.

### 1\. Create the Network Source

Follow the instructions provided for the Console or the API to create the network source.

A single network source can include IP addresses from a specific VCN, public IP addresses, or both.

To specify the VCN, you need the VCN OCID and the subnet IP ranges that you want to allow.

Examples:

  - **Public IP addresses or CIDR blocks:** 192.0.2.143 or 192.0.2.0/24
  - **VCN OCID:** ocid1.vcn.oc1.iad.aaaaaaaaexampleuniqueID
      - **Subnet IP addresses or CIDR blocks:** 10.0.0.4, 10.0.0.0/16
        
        To allow any IP address from a specific VCN, use 0.0.0.0/0.

### 2\. Write the Policy

The IAM service includes a variable to use in policy that allows you to scope your policy using a condition. The variable is:

`request.networkSource.name`

After you have created your network source, you can scope policies by using this variable in a condition. For example, assume you create a network source named "corpnet". You can restrict users of the group "CorporateUsers" to access your Object Storage resources only when their requests originate from IP addresses you specified in corpnet. To do this, write a policy like the following:

    allow group CorporateUsers to manage object-family in tenancy where request.networkSource.name='corpnet'

This policy allows users in the CorporateUsers group to manage Object Storage resources only when their requests originate from an allowed IP address specified in the network source "corpnet". Requests made from outside the specified IP ranges are denied. For general information about writing policies, see How Policies Work.