---
title: "IAM JSON policy elements: Effect"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_effect.html"
fetched: "20260306T011517Z"
---

# IAM JSON policy elements: Effect

The `Effect` element is required and specifies whether the statement results in an allow or an explicit deny. Valid values for `Effect` are `Allow` and `Deny`. The `Effect` value is case sensitive.

    "Effect":"Allow"

By default, access to resources is denied. To allow access to a resource, you must set the `Effect` element to `Allow`. To override an allow (for example, to override an allow that is otherwise in force), you set the `Effect` element to `Deny`. For more information, see Policy evaluation logic.