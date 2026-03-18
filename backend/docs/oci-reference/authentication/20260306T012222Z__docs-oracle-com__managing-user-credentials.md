---
title: "Managing User Credentials"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcredentials.htm"
fetched: "20260306T012222Z"
---

### **Easier to use**

Database end users can easily use IAM database passwords because they can continue to use a well-known authentication method to access the database. You can access database passwords that you manage through your OCI profile after you successfully authenticate to OCI.

Before users can access or manage their database password, IAM administrators can create an extra layer of protection by enforcing multifactor authentication using Managing Multifactor Authentication. For example, this can be a FIDO authenticator, or by pushing notifications through authenticator applications.

### IAM Database Password Security

Using IAM database usernames and IAM database passwords to access databases improves security because they allow IAM administrators to centrally manage users and user access to database passwords within IAM instead of locally in each database. When a user leaves an organization, their IAM account is suspended and therefore, their access to all databases are automatically suspended. This method removes the possibility of unauthorized accounts being left on database servers after a user has left. For more information, see IAM Database Passwords. See the Oracle Security Guide, Chapter 7 for information about how IAM users authenticate and authorize to OCI databases.

### IAM Database User Names

If your OCI IAM database username is longer than 128 bytes, you must set a different database username and a database password that is less than 128 bytes. IAM enforces the uniqueness of database usernames within a tenancy. The database user name is not case-sensitive and has the same allowable characters as an IAM user name (ASCII letters, numerals, hyphens, periods, underscores, +, and @)). This is more restrictive than local database usernames, which are governed by the character set of the database. See Database Object Names and Qualifiers for more information.

To create, change, and delete IAM database user names, see Working with IAM Database User Names.

### Alternate IAM Database User Names

You can create an alternate IAM database user name that contains only letters and numbers, does not include special characters, and can be shorter than regular IAM database user names.

You can create an alternate IAM database user name:

  - If your user name is too long or hard to type
  - To make logging in easier with a user name that does not include special characters

### **IAM Database Password Specifications**

The IAM database password complexity uses almost the same rules supported in IAM for Console passwords (no double quotes \["\] in IAM passwords). For details, see Creating an IAM database password.

### **Password Rollovers**

Applications have a password in a wallet or other secure mechanism and in the database. When changing a database password, you also need to change the password in the application wallet. You normally do this during application downtime. However, having a second password allows you to change passwords without application downtime. Since both passwords are usable, the application admin can swap passwords in the application wallet files at their convenience, and can remove the old password from IAM later. This is independent of the database gradual password rollover status in the database. The database still reflects open status, that is, not open and in rollover.