---
title: "AWS Identity and Access Management"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users.html"
fetched: "20260306T011558Z"
---

# IAM users

IAM best practices recommend that you require human users to use federation with an identity provider to access AWS using temporary credentials instead of using IAM users with long-term credentials. We recommend that you only use IAM users for specific use cases not supported by federated users.

An *IAM user* is an entity that you create in your AWS account. The IAM user represents the human user or workload who uses the IAM user to interact with AWS resources. An IAM user consists of a name and credentials.

An IAM user with administrator permissions is not the same thing as the AWS account root user. For more information about the root user, see AWS account root user.

## How AWS identifies an IAM user

When you create an IAM user, IAM creates these ways to identify that user:

  - A "friendly name" for the IAM user, which is the name that you specified when you created the IAM user, such as `Richard` or `Anaya`. These are the names you see in the AWS Management Console. Because IAM user names appear in Amazon Resource Names (ARNs), we do not recommend including personally identifying information in the IAM name. Refer to IAM name requirements for requirements and restrictions for IAM names.

  - An Amazon Resource Name (ARN) for the IAM user. You use the ARN when you need to uniquely identify the IAM user across all of AWS. For example, you could use an ARN to specify the IAM user as a `Principal` in an IAM policy for an Amazon S3 bucket. An ARN for an IAM user might look like the following:
    
    `arn:aws:iam::account-ID-without-hyphens`:user/Richard

  - A unique identifier for the IAM user. This ID is returned only when you use the API, Tools for Windows PowerShell, or AWS CLI to create the IAM user; you do not see this ID in the console.

For more information about these identifiers, see IAM identifiers.

## IAM users and credentials

You can access AWS in different ways depending on the IAM user credentials:

  - Console password: A password that the IAM user can type to sign in to interactive sessions such as the AWS Management Console. Disabling the password (console access) for an IAM user prevents them from signing in to the AWS Management Console using their sign-in credentials. It does not change their permissions or prevent them from accessing the console using an assumed role. IAM users with console access enabled can also use these same credentials to authenticate for AWS CLI and SDK access using the `aws login` AWS CLI command. These users will need to have SignInLocalDevelopmentAccess permissions. See Authentication and access credentials for the AWS CLI in the *AWS Command Line Interface User Guide* for more details.

  - Access keys: Used to make programmatic calls to AWS. However, there are more secure alternatives to consider before you create access keys for IAM users. For more information, see Considerations and alternatives for long-term access keys in the *AWS General Reference*. If the IAM user has active access keys, they continue to function and allow access through the AWS CLI, Tools for Windows PowerShell, AWS API, or the AWS Console Mobile Application.

  - SSH keys for use with CodeCommit: An SSH public key in the OpenSSH format that can be used to authenticate with CodeCommit.

  - Server certificates: SSL/TLS certificates that you can use to authenticate with some AWS services. We recommend that you use AWS Certificate Manager (ACM) to provision, manage, and deploy your server certificates. Use IAM only when you must support HTTPS connections in a region that is not supported by ACM. To learn which regions support ACM, see AWS Certificate Manager endpoints and quotas in the *AWS General Reference*.

You can choose the credentials that are right for your IAM user. When you use the AWS Management Console to create an IAM user, you must choose to at least include a console password or access keys. By default, a brand new IAM user created using the AWS CLI or AWS API has no credentials of any kind. You must create the type of credentials for an IAM user based on your use case.

You have the following options to administer passwords, access keys, and multi-factor authentication (MFA) devices:

  - **Manage passwords for your IAM users.** Create and change the passwords that permit access to the AWS Management Console. Set a password policy to enforce a minimum password complexity. Allow IAM users to change their own passwords.

  - **Manage access keys for your IAM users.** Create and update access keys for programmatic access to the resources in your account.

  - **Enable multi-factor authentication (MFA) for the IAM user.** As a best practice, we recommend that you require multi-factor authentication for all IAM users in your account. With MFA, IAM users must provide two forms of identification: First, they provide the credentials that are part of their user identity (a password or access key). In addition, they provide a temporary numeric code that's generated on a hardware device or by an application on a smartphone or tablet.

  - **Find unused passwords and access keys.** Anyone who has a password or access keys for your account or an IAM user in your account has access to your AWS resources. The security best practice is to remove passwords and access keys when IAM users no longer need them.

  - **Download a credential report for your account.** You can generate and download a credential report that lists all IAM users in your account and the status of their various credentials, including passwords, access keys, and MFA devices. For passwords and access keys, the credential report shows how recently the password or access key has been used.

## IAM users and permissions

By default, a new IAM user has no permissions to do anything. They are not authorized to perform any AWS operations or to access any AWS resources. An advantage of having individual IAM users is that you can assign permissions individually to each user. You might assign administrative permissions to a few users, who then can administer your AWS resources and can even create and manage other IAM users. In most cases, however, you want to limit a user's permissions to just the tasks (AWS actions or operations) and resources that are needed for the job.

Imagine a user named Diego. When you create the IAM user `Diego`, you create a password for him and attach permissions that let him launch a specific Amazon EC2 instance and read (`GET`) information from a table in an Amazon RDS database. For procedures on how to create IAM users and grant them initial credentials and permissions, see Create an IAM user in your AWS account. For procedures on how to change the permissions for existing users, see Change permissions for an IAM user. For procedures on how to change the user's password or access keys, see User passwords in AWS and Manage access keys for IAM users.

You can also add a permissions boundary to your IAM users. A permissions boundary is an advanced feature that allows you to use AWS managed policies to limit the maximum permissions that an identity-based policy can grant to an IAM user or role. For more information about policy types and uses, see Policies and permissions in AWS Identity and Access Management.

## IAM users and accounts

Each IAM user is associated with one and only one AWS account. Because IAM users are defined within your AWS account, they don't need to have a payment method on file with AWS. Any AWS activity performed by IAM users in your account is billed to your account.

The number and size of IAM resources in an AWS account are limited. For more information, see IAM and AWS STS quotas.

## IAM users as service accounts

An IAM user is a resource in IAM that has associated credentials and permissions. An IAM user can represent a person or an application that uses its credentials to make AWS requests. This is typically referred to as a *service account*. If you choose to use the long-term credentials of an IAM user in your application, **do not embed access keys directly into your application code.** The AWS SDKs and the AWS Command Line Interface allow you to put access keys in known locations so that you do not have to keep them in code. For more information, see Manage IAM User Access Keys Properly in the *AWS General Reference*. Alternatively, and as a best practice, you can use temporary security credentials (IAM roles) instead of long-term access keys.