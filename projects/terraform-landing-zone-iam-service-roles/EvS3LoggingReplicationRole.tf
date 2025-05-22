data "aws_iam_policy_document" "ev_s3_logging_replication_policy" {
  version = "2012-10-17"
  statement {
    actions = [
      "s3:GetReplicationConfiguration",
      "s3:ListBucket",
      "s3:GetObjectVersion",
      "s3:GetObjectVersionAcl",
      "s3:ReplicateObject",
      "s3:ReplicateDelete",
      "s3:ObjectOwnerOverrideToBucketOwner"
    ]
    effect    = "Allow"
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ev_s3_logging_replication_policy" {
  name        = "EvS3LoggingReplicationPolicy"
  path        = "/"
  description = "Logging Account Replication Policy"
  policy      = data.aws_iam_policy_document.ev_s3_logging_replication_policy.json
}

data "aws_iam_policy_document" "ev_s3_logging_replication_role" {
  version = "2012-10-17"
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = ["s3.amazonaws.com"]
      type        = "Service"
    }
    effect = "Allow"
  }
}

resource "aws_iam_role" "ev_s3_logging_replication_role" {
  name               = "EvS3LoggingReplicationRole"
  path               = "/"
  description        = "Logging Account Replication Role"
  assume_role_policy = data.aws_iam_policy_document.ev_s3_logging_replication_role.json

  tags = merge(var.tags, {
    "Name" = "EvS3LoggingReplicationRole"
  })
}

resource "aws_iam_role_policy_attachment" "EvS3LoggingReplicationPolicy_EvS3LoggingReplicationRole_policy_attachment" {
  policy_arn = aws_iam_policy.ev_s3_logging_replication_policy.arn
  role       = aws_iam_role.ev_s3_logging_replication_role.name
}
