---
title: "IAM JSON policy elements: Resource"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_resource.html"
fetched: "20260306T011517Z"
---

# IAM JSON policy elements: Resource

The `Resource` element in an IAM policy statement defines the object or objects that the statement applies to. Statements must include either a `Resource` or a `NotResource` element.

You specify a resource using an Amazon Resource Name (ARN). The format of the ARN depends on the AWS service and the specific resource you're referring to. Although the ARN format varies you always use an ARN to identify a resource. For more information about the format of ARNs, see IAM ARNs. For information about how to specify a resource, refer to the documentation for the service you want to write a statement.

Some AWS services do not allow you to specify actions for individual resources. In these cases, any actions that you list in the `Action` or `NotAction` element apply to all resources in that service. When this is the case, you use the wildcard character (`*`) in the `Resource` element.

The following example refers to a specific Amazon SQS queue.

    "Resource": "arn:aws:sqs:us-east-2:account-ID-without-hyphens:queue1"

The following example refers to the IAM user named `Bob` in an AWS account.

In the `Resource` element, the IAM user name is case sensitive.

    "Resource": "arn:aws:iam::account-ID-without-hyphens:user/Bob"

## Using wildcards in resource ARNs

You can use wildcard characters (`*` and `?`) within the individual segments of an ARN (the parts separated by colons) to represent:

You can use multiple `*` or `?` characters in each segment. If the `*` wildcard is the last character of a resource ARN segment, it can expand to match beyond the colon boundaries. We recommend you use wildcards (`*` and `?`) within ARN segments separated by a colon.

The following example refers to all IAM users whose path is `/accounting`.

    "Resource": "arn:aws:iam::account-ID-without-hyphens:user/accounting/*"

The following example refers to all items within a specific Amazon S3 bucket.

    "Resource": "arn:aws:s3:::amzn-s3-demo-bucket/*"

The asterisk (`*`) character can expand to replace everything within a segment, including characters like a forward slash (`/`) that may otherwise appear to be a delimiter within a given service namespace. For example, consider the following Amazon S3 ARN as the same wildcard expansion logic applies to all services.

    "Resource": "arn:aws:s3:::amzn-s3-demo-bucket/*/test/*"

The wildcards in the ARN apply to all of the following objects in the bucket, not only the first object listed.

    amzn-s3-demo-bucket/1/test/object.jpg
    amzn-s3-demo-bucket/1/2/test/object.jpg
    amzn-s3-demo-bucket/1/2/test/3/object.jpg 
    amzn-s3-demo-bucket/1/2/3/test/4/object.jpg
    amzn-s3-demo-bucket/1///test///object.jpg
    amzn-s3-demo-bucket/1/test/.jpg
    amzn-s3-demo-bucket//test/object.jpg
    amzn-s3-demo-bucket/1/test/

Consider the last two objects in the previous list. An Amazon S3 object name can begin or end with the conventional delimiter forward slash (`/`) character. While `/` works as a delimiter, there is no specific significance when this character is used within a resource ARN. It is treated the same as any other valid character. The ARN would not match the following objects:

    amzn-s3-demo-bucket/1-test/object.jpg
    amzn-s3-demo-bucket/test/object.jpg
    amzn-s3-demo-bucket/1/2/test.jpg

## Specifying multiple resources

You can specify multiple resources in the `Resource` element by using an array of ARNs. The following example refers to two DynamoDB tables.

    "Resource": [
        "arn:aws:dynamodb:us-east-2:account-ID-without-hyphens:table/books_table",
        "arn:aws:dynamodb:us-east-2:account-ID-without-hyphens:table/magazines_table"
    ]

## Using policy variables in resource ARNs

In the `Resource` element, you can use JSON policy variables in the part of the ARN that identifies the specific resource (that is, in the trailing part of the ARN). For example, you can use the key `{aws:username}` as part of a resource ARN to indicate that the current user's name should be included as part of the resource's name. The following example shows how you can use the `{aws:username}` key in a `Resource` element. The policy allows access to a Amazon DynamoDB table that matches the current user's name.

  - JSON
    
    
    
      - ****
        
            {
                "Version":"2012-10-17",              
                "Statement": {
                    "Effect": "Allow",
                    "Action": "dynamodb:*",
                    "Resource": "arn:aws:dynamodb:us-east-2:111122223333:table/${aws:username}"
                }
            }
    
    

For more information about JSON policy variables, see IAM policy elements: Variables and tags.