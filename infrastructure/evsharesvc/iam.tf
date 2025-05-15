data "aws_iam_policy_document" "cidb_kms_key_policy" {
  version   = "2012-10-17"
  policy_id = "cidb-default-1"
  statement {
    sid    = "AWSConfigKMSPolicy"
    effect = "Allow"
    principals {
      identifiers = [
        "config.amazonaws.com",
        "lambda.amazonaws.com"
      ]
      type = "Service"
    }
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
      "kms:Encrypt"
    ]
    resources = [
      "arn:aws:kms:*:477591219415:key/mrk-3203c4f8461047feae1c17579a2548c4",
      "arn:aws:kms:*:435574127453:key/mrk-efe61e82706249188b2173380434c46a"

    ]
  }
  statement {
    sid    = "AllowAdminofKey"
    effect = "Allow"
    principals {
      identifiers = [
        "*"
      ]
      type = "AWS"
    }
    actions = [
      "kms:*"
    ]
    resources = [
      "*"
    ]
    condition {
      test = "StringEquals"
      values = [
        "arn:aws:iam::477591219415:role/OrganizationAccountAccessRole",
        "arn:aws:iam::477591219415:role/${var.short_env}-us-east-1-selfhosted-runner-role",
        "arn:aws:iam::435574127453:role/OrganizationAccountAccessRole",
        "arn:aws:iam::435574127453:role/${var.short_env}-us-east-1-selfhosted-runner-role",
      ]
      variable = "aws:PrincipalArn"
    }
  }
  statement {
    sid    = "AllowUseOfKey"
    effect = "Allow"
    principals {
      identifiers = [
        "*"
      ]
      type = "AWS"
    }
    actions = [
      "kms:Decrypt"
    ]
    resources = [
      "*"
    ]
    condition {
      test = "StringEquals"
      values = [
        "arn:aws:iam::435574127453:role/CidbReplicationRole",
        "arn:aws:iam::477591219415:role/CidbReplicationRole",
        module.cidb2-infra.cidb2_lambda_role_arn
      ]
      variable = "aws:PrincipalArn"
    }
  }
  statement {
    sid    = "AllowUseOfKeyByCIDBAMIInventoryLambda"
    effect = "Allow"
    principals {
      identifiers = [
        "*"
      ]
      type = "AWS"
    }
    actions = [
      "kms:Encrypt",
      "kms:GenerateDataKey"
    ]
    resources = [
      "*"
    ]
    condition {
      test = "StringEquals"
      values = [
        aws_iam_role.ev_ms_cidb_ami_inventory_role.arn,
        module.cidb2-infra.cidb2_lambda_role_arn
      ]
      variable = "aws:PrincipalArn"
    }
  }
  statement {
    sid    = "EngineerRoleDownloadUploadObject"
    effect = "Allow"
    principals {
      identifiers = [
        "*"
      ]
      type = "AWS"
    }
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey",
      "kms:DescribeKey"
    ]
    resources = [
      "*"
    ]
    condition {
      test = "StringEquals"
      values = [
        local.engineer_role_arn
      ]
      variable = "aws:PrincipalArn"
    }
  }
}

data "aws_iam_policy_document" "cidb_key_creds" {
  version = "2012-10-17"
  statement {
    sid    = "AllowGetSecret"
    effect = "Allow"
    principals {
      identifiers = ["arn:aws:iam::${module.defaults.account_id}:role/CidbReplicationRole", ]
      type        = "AWS"
    }
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      values   = [data.aws_organizations_organization.current.id]
      variable = "aws:PrincipalOrgID"
    }
  }
}
