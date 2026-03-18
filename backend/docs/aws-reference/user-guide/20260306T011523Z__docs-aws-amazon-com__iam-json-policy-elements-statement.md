---
title: "IAM JSON policy elements: Statement"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_statement.html"
fetched: "20260306T011523Z"
---

# IAM JSON policy elements: Statement

The `Statement` element is the main element for a policy. This element is required. The `Statement` element can contain a single statement or an array of individual statements. Each individual statement block must be enclosed in curly braces {Â }. For multiple statements, the array must be enclosed in square brackets \[Â \].

    "Statement": [{...},{...},{...}]

The following example shows a policy that contains an array of three statements inside a single `Statement` element. (The policy allows you to access your own "home folder" in the Amazon S3 console.) The policy includes the `aws:username` variable, which is replaced during policy evaluation with the user name from the request. For more information, see Introduction.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Effect": "Allow",
                  "Action": [
                    "s3:ListAllMyBuckets",
                    "s3:GetBucketLocation"
                  ],
                  "Resource": "arn:aws:s3:::*"
                },
                {
                  "Effect": "Allow",
                  "Action": "s3:ListBucket",
                  "Resource": "arn:aws:s3:::amzn-s3-demo-bucket",
                  "Condition": {"StringLike": {"s3:prefix": [
                    "",
                    "home/",
                    "home/${aws:username}/"
                  ]}}
                },
                {
                  "Effect": "Allow",
                  "Action": "s3:*",
                  "Resource": [
                    "arn:aws:s3:::amzn-s3-demo-bucket/home/${aws:username}",
                    "arn:aws:s3:::amzn-s3-demo-bucket/home/${aws:username}/*"
                  ]
                }
              ]
            }