data "aws_iam_policy_document" "ev_limited_access_policy" {
  version = "2012-10-17"
  ## RoleChangeBoundary
  statement {
    sid    = "RoleChangeBoundary"
    effect = "Deny"
    actions = [
      "iam:PutRolePermissionsBoundary",
      "iam:DeleteRolePermissionsBoundary"
    ]
    resources = ["*"]
  }
  ## AWSMarketplaceBoundary
  statement {
    sid       = "AWSMarketplaceBoundary"
    effect    = "Deny"
    actions   = ["aws-marketplace:*"]
    resources = ["*"]
  }
  ## ServiceLinkedRoleBoundary
  statement {
    sid    = "ServiceLinkedRoleBoundary"
    effect = "Deny"
    actions = [
      "iam:CreateServiceLinkedRole"
    ]
    resources = ["*"]
    condition {
      test = "StringEquals"
      values = [
        "cloudtrail.amazonaws.com",
        "organizations.amazonaws.com",
        "s2svpn.amazonaws.com",
        "transitgateway.amazonaws.com",
        "globalaccelerator.amazonaws.com"
      ]
      variable = "iam:AWSServiceName"
    }
  }
  ## ManagedPolicyAttachmentBoundary
  statement {
    sid       = "ManagedPolicyAttachmentBoundary"
    effect    = "Deny"
    actions   = ["iam:AttachRolePolicy"]
    resources = ["*"]
    condition {
      test = "ArnEquals"
      values = [
        "arn:aws:iam::aws:policy/AdministratorAccess",
        "arn:aws:iam::aws:policy/*IAM*",
        "arn:aws:iam::aws:policy/*CloudTrail*",
        "arn:aws:iam::aws:policy/*Organizations*",
        "arn:aws:iam::aws:policy/*VPC*",
        "arn:aws:iam::aws:policy/*CloudFront*",
        "arn:aws:iam::aws:policy/*GlobalAccelerator*"
      ]
      variable = "iam:PolicyARN"
    }
    condition {
      test = "ArnNotEquals"
      values = [
        "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole",
        "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
      ]
      variable = "iam:PolicyARN"
    }
  }
  ## EC2RunInstancesRestriction
  statement {
    sid       = "EC2RunInstancesRestriction"
    effect    = "Deny"
    actions   = ["ec2:RunInstances"]
    resources = ["arn:aws:ec2:*:*:subnet/*"]
    condition {
      test     = "StringEquals"
      values   = ["Transit"]
      variable = "ec2:ResourceTag/Accessibility"
    }
  }

  ## LimitInstanceTypes
  statement {
    sid    = "LimitInstanceTypes"
    effect = "Deny"
    actions = [
      "ec2:RunInstances",
      "ec2:ModifyInstanceAttribute"
    ]
    resources = ["arn:aws:ec2:*:*:instance/*"]
    condition {
      test = "StringNotLike"
      values = [
        "*.nano",
        "*.small",
        "*.micro",
        "*.medium",
        "*.large",
        "*.xlarge"
      ]
      variable = "ec2:InstanceType"
    }
    condition {
      test = "StringNotLike"
      values = [
        "arn:aws:iam::*:role/*-selfhosted-runner-role",
        "arn:aws:iam::*:role/*Gitlab_Runner*",
        "arn:aws:iam::*:role/*GitLabEKSRunner*EC2Worker",
        "arn:aws:iam::*:role/*GitlabEKSRunner*EC2Worker"
      ]
      variable = "aws:PrincipalArn"
    }

  }

  ## limit ModifyLaunchTemplate
  statement {
    sid    = "LimitModifyLaunch"
    effect = "Deny"
    actions = [
      "ec2:ModifyLaunchTemplate"
    ]
    resources = ["arn:*:ec2:*:*:launch-template/*"]
    condition {
      test = "StringNotLike"
      values = [
        "arn:aws:iam::*:role/*-selfhosted-runner-role",
        "arn:aws:iam::*:role/*Gitlab_Runner*",
        "arn:aws:iam::*:role/*GitLabEKSRunner*EC2Worker",
        "arn:aws:iam::*:role/*GitlabEKSRunner*EC2Worker"
      ]
      variable = "aws:PrincipalArn"
    }
  }

  ## LimitInstanceVolumeSize
  dynamic "statement" {
    for_each = local.enable_sandbox ? toset(compact(["sandbox"])) : toset(compact([""]))
    content {
      sid       = "LimitInstanceVolumeSize"
      effect    = "Allow"
      actions   = ["ec2:RunInstances"]
      resources = ["arn:aws:ec2:*:*:volume/*"]
      condition {
        test     = "NumericLessThanEquals"
        values   = ["200"]
        variable = "ec2:VolumeSize"
      }
      condition {
        test = "StringNotLike"
        values = [
          "arn:aws:iam::*:role/*-selfhosted-runner-role",
          "arn:aws:iam::*:role/*GitLabEKSRunner*EC2Worker",
          "arn:aws:iam::*:role/*GitlabEKSRunner*EC2Worker",
          "arn:aws:iam::*:role/*Gitlab_Runner*"

        ]
        variable = "aws:PrincipalArn"
      }

    }
  }
}

resource "aws_iam_policy" "ev_limited_access_policy" {
  name        = "EVLimitedAccessPolicy"
  path        = local.path
  description = "Restricted access to approved services."
  policy      = data.aws_iam_policy_document.ev_limited_access_policy.json
}
