data "aws_iam_policy_document" "assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "cidb-replication-role-tf" {
  name               = "CidbReplicationRole"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "policy" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetReplicationConfiguration",
      "s3:ListBucket",
      "s3:PutInventoryConfiguration"
    ]
    resources = ["arn:aws:s3:::${module.defaults.account_alias}-${var.region}-${local.accessibility}-${var.bucket_alias}"]
  }
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObjectVersion",
      "s3:GetObject",
      "s3:GetObjectVersionAcl",
      "s3:GetObjectVersionForReplication",
      "s3:GetObjectVersionTagging"
    ]
    resources = ["arn:aws:s3:::${module.defaults.account_alias}-${var.region}-${local.accessibility}-${var.bucket_alias}/*"]
  }
  statement {
    effect = "Allow"
    actions = [
      "s3:ReplicateObject",
      "s3:ReplicateDelete",
      "s3:ReplicateTags",
      "s3:GetObjectVersionTagging",
      "s3:ObjectOwnerOverrideToBucketOwner"
    ]
    resources = ["${var.dest_bucket_arn}/*"]
  }
  statement {
    effect = "Allow"
    actions = [
      "s3:List*",
      "s3:GetBucketVersioning",
      "s3:PutBucketVersioning"
    ]
    resources = ["${var.dest_bucket_arn}"]
  }
  statement {
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey"
    ]
    resources = [
      "${var.dest_bucket_kms_arn}",
      aws_kms_key.cidb_app_source_bucket_key.arn
    ]
  }
}

resource "aws_iam_policy" "replication_policy" {
  name        = "cidb-replication-policy"
  description = "This is the replication policy for cidb role"
  policy      = data.aws_iam_policy_document.policy.json
}

resource "aws_iam_role_policy_attachment" "replication_policy_attach" {
  role       = aws_iam_role.cidb-replication-role-tf.name
  policy_arn = aws_iam_policy.replication_policy.arn
}
