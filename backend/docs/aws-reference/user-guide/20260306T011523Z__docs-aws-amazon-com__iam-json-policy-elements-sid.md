---
title: "IAM JSON policy elements: Sid"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_sid.html"
fetched: "20260306T011523Z"
---

# IAM JSON policy elements: Sid

You can provide a `Sid` (statement ID) as an optional identifier for the policy statement. You can assign a `Sid` value to each statement in a statement array. You can use the `Sid` value as a description for the policy statement. In services that let you specify an `ID` element, such as SQS and SNS, the `Sid` value is just a sub-ID of the policy document ID. In IAM, the `Sid` value must be unique within a JSON policy.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Sid": "ExampleStatementID",
                  "Effect": "Allow",
                  "Action": "s3:ListAllMyBuckets",
                  "Resource": "*"
                }
              ]
            }
    
    

The `Sid` element supports ASCII uppercase letters (A-Z), lowercase letters (a-z), and numbers (0-9).

IAM does not expose the `Sid` in the IAM API. You can't retrieve a particular statement based on this ID.

Some AWS services (for example, Amazon SQS or Amazon SNS) might require this element and have uniqueness requirements for it. For service-specific information about writing policies, refer to the documentation for the service you work with.