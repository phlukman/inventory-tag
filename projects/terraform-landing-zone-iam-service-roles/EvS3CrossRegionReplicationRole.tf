data "aws_iam_policy_document" "ev_s3_cross_region_replication_policy" {
  version = "2012-10-17"
  statement {
    actions = [
      "s3:GetReplicationConfiguration",
      "s3:ListBucket",
      "s3:GetObjectVersion",
      "s3:GetObjectVersionAcl",
      "s3:ReplicateObject",
      "s3:ReplicateDelete"
    ]
    effect    = "Allow"
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ev_s3_cross_region_replication_policy" {
  name        = "EvS3CrossRegionReplicationPolicy"
  path        = "/"
  description = "Cross Region Replication Policy"
  policy      = data.aws_iam_policy_document.ev_s3_cross_region_replication_policy.json
}

data "aws_iam_policy_document" "ev_s3_cross_region_replication_role" {
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

resource "aws_iam_role" "ev_s3_cross_region_replication_role" {
  name               = "EvS3CrossRegionReplicationRole"
  assume_role_policy = data.aws_iam_policy_document.ev_s3_cross_region_replication_role.json
  path               = "/"
  tags = merge(var.tags, {
    Name = "EvS3CrossRegionReplicationRole"
  })
}

resource "aws_iam_role_policy_attachment" "EvS3CrossRegionReplicationPolicy_evs3crossregionreplicationrole_policy_attachment" {
  role       = aws_iam_role.ev_s3_cross_region_replication_role.name
  policy_arn = aws_iam_policy.ev_s3_cross_region_replication_policy.arn
}
