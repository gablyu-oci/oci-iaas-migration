---
title: "Conditions with multiple context keys or values"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_multi-value-conditions.html"
fetched: "20260306T011459Z"
---

# Conditions with multiple context keys or values

You can use the `Condition` element of a policy to test multiple context keys or multiple values for a single context key in a request. When you make a request to AWS, either programmatically or through the AWS Management Console, your request includes information about your principal, operation, tags, and more. You can use context keys to test the values of the matching context keys in the request, with the context keys specified in the policy condition. To learn about information and data included in a request, see The request context.

## Evaluation logic for multiple context keys or values

A `Condition` element can contain multiple condition operators, and each condition operator can contain multiple context key-value pairs. Most context keys support using multiple values, unless otherwise specified.

  - If your policy statement has multiple condition operators, the condition operators are evaluated using a logical `AND`.

  - If your policy statement has multiple context keys attached to a single condition operator, the context keys are evaluated using a logical `AND`.

  - If a single condition operator includes multiple values for a context key, those values are evaluated using a logical `OR`.

  - If a single negated matching condition operator includes multiple values for a context key, those values are evaluated using a logical `NOR`.

All context keys in a condition element block must resolve to true to invoke the desired `Allow` or `Deny` effect. The following figure illustrates the evaluation logic for a condition with multiple condition operators and context key-value pairs.

For example, the following S3 bucket policy illustrates how the previous figure is represented in a policy. The condition block includes condition operators `StringEquals` and `ArnLike`, and context keys `aws:PrincipalTag` and `aws:PrincipalArn`. To invoke the desired `Allow` or `Deny` effect, all context keys in the condition block must resolve to true. The user making the request must have both principal tag keys, *department* and *role*, that include one of the tag key values specified in the policy. Also, the principal ARN of the user making the request must match one of the `aws:PrincipalArn` values specified in the policy to be evaluated as true.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Sid": "ExamplePolicy",
                  "Effect": "Allow",
                  "Principal": {
                    "AWS": "arn:aws:iam::222222222222:root"
                  },
                  "Action": "s3:ListBucket",
                  "Resource": "arn:aws:s3:::amzn-s3-demo-bucket",
                  "Condition": {
                    "StringEquals": {
                      "aws:PrincipalTag/department": [
                        "finance",
                        "hr",
                        "legal"
                      ],
                      "aws:PrincipalTag/role": [
                        "audit",
                        "security"
                      ]
                    },
                    "ArnLike": {
                      "aws:PrincipalArn": [
                        "arn:aws:iam::222222222222:user/Ana",
                        "arn:aws:iam::222222222222:user/Mary"
                      ]
                    }
                  }
                }
              ]
            }
    
    

The following table shows how AWS evaluates this policy based on the condition key values in your request.

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr class="header">
<th>Policy Condition</th>
<th>Request Context</th>
<th>Result</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td><pre><code>aws:PrincipalTag/department: legal
aws:PrincipalTag/role: audit
aws:PrincipalArn: 
  arn:aws:iam::222222222222:user/Mary</code></pre></td>
<td><p><strong>Match</strong></p></td>
</tr>
<tr class="even">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td><pre><code>aws:PrincipalTag/department: hr
aws:PrincipalTag/role: audit
aws:PrincipalArn:
  arn:aws:iam::222222222222:user/Nikki</code></pre></td>
<td><p><strong>No match</strong></p></td>
</tr>
<tr class="odd">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td><pre><code>aws:PrincipalTag/department: hr
aws:PrincipalTag/role: payroll
aws:PrincipalArn:
  arn:aws:iam::222222222222:user/Mary</code></pre></td>
<td><p><strong>No match</strong></p></td>
</tr>
<tr class="even">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td><p>No <code>aws:PrincipalTag/role</code> in the request context.</p>
<pre><code>aws:PrincipalTag/department: hr
aws:PrincipalArn:
  arn:aws:iam::222222222222:user/Mary</code></pre></td>
<td><p><strong>No match</strong></p></td>
</tr>
<tr class="odd">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td><p>No <code>aws:PrincipalTag</code> in the request context.</p>
<pre><code>aws:PrincipalArn:
  arn:aws:iam::222222222222:user/Mary</code></pre></td>
<td><p><strong>No match</strong></p></td>
</tr>
</tbody>
</table>

## Evaluation logic for negated matching condition operators

Some condition operators, such as `StringNotEquals` or `ArnNotLike`, use negated matching to compare the context key-value pairs in your policy against the context key-value pairs in a request. When multiple values are specified for a single context key in a policy with negated matching condition operators, the effective permissions work like a logical `NOR`. In negated matching, a logical `NOR` or `NOT         OR` returns true only if all values evaluate to false.

The following figure illustrates the evaluation logic for a condition with multiple condition operators and context key-value pairs. The figure includes a negated matching condition operator for context key 3.

For example, the following S3 bucket policy illustrates how the previous figure is represented in a policy. The condition block includes condition operators `StringEquals` and `ArnNotLike`, and context keys `aws:PrincipalTag` and `aws:PrincipalArn`. To invoke the desired `Allow` or `Deny` effect, all context keys in the condition block must resolve to true. The user making the request must have both principal tag keys, *department* and *role*, that include one of the tag key values specified in the policy. Since the `ArnNotLike` condition operator uses negated matching, the principal ARN of the user making the request must not match any of the `aws:PrincipalArn` values specified in the policy to be evaluated as true.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Sid": "ExamplePolicy",
                  "Effect": "Allow",
                  "Principal": {
                    "AWS": "arn:aws:iam::222222222222:root"
                  },
                  "Action": "s3:ListBucket",
                  "Resource": "arn:aws:s3:::amzn-s3-demo-bucket",
                  "Condition": {
                    "StringEquals": {
                      "aws:PrincipalTag/department": [
                        "finance",
                        "hr",
                        "legal"
                      ],
                      "aws:PrincipalTag/role": [
                        "audit",
                        "security"
                      ]
                    },
                    "ArnNotLike": {
                      "aws:PrincipalArn": [
                        "arn:aws:iam::222222222222:user/Ana",
                        "arn:aws:iam::222222222222:user/Mary"
                      ]
                    }
                  }
                }
              ]
            }
    
    

The following table shows how AWS evaluates this policy based on the condition key values in your request.

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr class="header">
<th>Policy Condition</th>
<th>Request Context</th>
<th>Result</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnNotLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td><pre><code>aws:PrincipalTag/department: legal
aws:PrincipalTag/role: audit
aws:PrincipalArn:
  arn:aws:iam::222222222222:user/Nikki</code></pre></td>
<td><p><strong>Match</strong></p></td>
</tr>
<tr class="even">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnNotLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td><pre><code>aws:PrincipalTag/department: hr
aws:PrincipalTag/role: audit
aws:PrincipalArn:
  arn:aws:iam::222222222222:user/Mary</code></pre></td>
<td><p><strong>No match</strong></p></td>
</tr>
<tr class="odd">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnNotLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td><pre><code>aws:PrincipalTag/department: hr
aws:PrincipalTag/role: payroll
aws:PrincipalArn:
  arn:aws:iam::222222222222:user/Nikki</code></pre></td>
<td><p><strong>No match</strong></p></td>
</tr>
<tr class="even">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnNotLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td>&gt;
<p>No <code>aws:PrincipalTag/role</code> in the request context.</p>
<pre><code>aws:PrincipalTag/department: hr
aws:PrincipalArn:
  arn:aws:iam::222222222222:user/Nikki</code></pre></td>
<td><p><strong>No match</strong></p></td>
</tr>
<tr class="odd">
<td><pre><code>&quot;StringEquals&quot;: {
  &quot;aws:PrincipalTag/department&quot;: [
    &quot;finance&quot;,
    &quot;hr&quot;,
    &quot;legal&quot;
  ],
  &quot;aws:PrincipalTag/role&quot;: [
    &quot;audit&quot;,
    &quot;security&quot;
  ]
},
&quot;ArnNotLike&quot;: {
  &quot;aws:PrincipalArn&quot;: [
      &quot;arn:aws:iam::222222222222:user/Ana&quot;,
      &quot;arn:aws:iam::222222222222:user/Mary&quot;
  ]
}</code></pre></td>
<td><p>No <code>aws:PrincipalTag</code> in the request context.</p>
<pre><code>aws:PrincipalArn:
  arn:aws:iam::222222222222:user/Nikki</code></pre></td>
<td><p><strong>No match</strong></p></td>
</tr>
</tbody>
</table>