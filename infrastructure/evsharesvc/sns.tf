# sns topic resources
module "cidb_sns_topic" {
  source          = "github.com/Eaton-Vance-Corp/terraform-aws-sns-topic?ref=v3.1.0"
  sns_topic_name  = "${var.short_env}-cidb-rep-fail-sns-topic"
  sns_policy_json = data.aws_iam_policy_document.cidb_sns_policy_json.json
  sns_kms_key_arn = aws_kms_key.sns_kms_key.arn
}

module "cidb_ami_sns_topic" {
  source          = "github.com/Eaton-Vance-Corp/terraform-aws-sns-topic?ref=v3.1.0"
  sns_topic_name  = "${var.short_env}-cidb-ami-fail-sns-topic"
  sns_policy_json = data.aws_iam_policy_document.cidb_sns_policy_json.json
  sns_kms_key_arn = aws_kms_key.sns_kms_key.arn
}

data "aws_iam_policy_document" "cidb_sns_policy_json" {
  version   = "2012-10-17"
  policy_id = "cidb_sns-topic-policy"

  statement {
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    actions = [
      "SNS:Subscribe",
      "SNS:SetTopicAttributes",
      "SNS:RemovePermission",
      "SNS:Receive",
      "SNS:Publish",
      "SNS:ListSubscriptionsByTopic",
      "SNS:GetTopicAttributes",
      "SNS:DeleteTopic",
      "SNS:AddPermission",
    ]
    effect    = "Allow"
    resources = ["*"]
  }
  statement {
    sid = "Allow cloudwatch to publish to sns"
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    actions = [
      "SNS:Publish"
    ]
    effect    = "Allow"
    resources = [module.cidb_ami_sns_topic.sns_topic.arn]
  }

}

module "sns_topic_subscription" {
  source        = "github.com/Eaton-Vance-Corp/terraform-aws-sns-topic?ref=v3.1.0/subscription"
  endpoint      = "cloud-im-bue-aws@morganstanley.com"
  protocol      = "email"
  sns_topic_arn = module.cidb_sns_topic.sns_topic.id
}

module "sns_topic_subscription_ami" {
  source        = "github.com/Eaton-Vance-Corp/terraform-aws-sns-topic?ref=v3.1.0/subscription"
  endpoint      = "cloud-im-bue-aws@morganstanley.com"
  protocol      = "email"
  sns_topic_arn = module.cidb_ami_sns_topic.sns_topic.id
}

# KMS key for SNS
resource "aws_kms_key" "sns_kms_key" {
  description             = "This key is used to encrypt cidb rep failure sns notifs"
  deletion_window_in_days = 10
  enable_key_rotation     = true
  multi_region            = false
  policy                  = data.aws_iam_policy_document.cidb_sns_kms_key_policy.json
  tags = {
    Name = "${var.short_env}-cidb-sns-kms-key"
  }
}

resource "aws_kms_alias" "cidb_sns_key_alias" {
  name          = "alias/${var.short_env}-cidb-sns-key"
  target_key_id = aws_kms_key.sns_kms_key.key_id
}

data "aws_iam_policy_document" "cidb_sns_kms_key_policy" {
  version = "2012-10-17"
  statement {
    sid    = "Enable IAM User Permissions"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.account_id}:root"]
    }
    actions   = ["kms:*"]
    resources = ["*"]
  }
  statement {
    sid    = "Allow S3 to use this key"
    effect = "Allow"
    principals {
      identifiers = [
        "s3.amazonaws.com",
        "lambda.amazonaws.com",
        "cloudwatch.amazonaws.com"

      ]
      type = "Service"
    }
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey"
    ]
    resources = [
      "*"
    ]
  }
}
