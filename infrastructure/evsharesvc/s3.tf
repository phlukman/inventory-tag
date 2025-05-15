module "cidb_s3_bucket" {
  source                     = "github.com/Eaton-Vance/terraform-aws-s3-bucket?ref=v4.1.5"
  accessibility              = "Private"
  account_alias              = module.defaults.account_alias
  account_id                 = module.defaults.account_id
  bucket_alias               = var.bucket_alias
  region                     = var.region
  sse_algorithm              = "aws:kms"
  s3_server_side_kms_key_arn = aws_kms_key.cidb_app_source_bucket_key.arn
}
data "aws_iam_policy_document" "cidb_ev_source_bucket_policy" {
  version   = "2012-10-17"
  policy_id = "cidb-source-bucket-policy"

  statement {
    sid    = "AWSBucketPermissionsCheck"
    effect = "Allow"
    principals {
      identifiers = [
        "config.amazonaws.com",
        "cloudtrail.amazonaws.com",
        "lambda.amazonaws.com"
      ]
      type = "Service"
    }
    actions = [
      "s3:GetBucketAcl",
      "s3:ListBucket"
    ]
    resources = [
      module.cidb_s3_bucket.s3_bucket.arn
    ]
  }
  statement {
    sid    = "AWSBucketDelivery"
    effect = "Allow"
    principals {
      identifiers = [
        "config.amazonaws.com",
        "cloudtrail.amazonaws.com",
        "lambda.amazonaws.com"
      ]
      type = "Service"
    }
    actions = [
      "s3:PutObject"
    ]
    resources = [
      "${module.cidb_s3_bucket.s3_bucket.arn}/*"
    ]
  }
  statement {
    sid    = "AWSBucketDelivery-1"
    effect = "Allow"
    principals {
      identifiers = [aws_iam_role.cidb-replication-role-tf.arn]
      type        = "AWS"
    }
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:ListBucketMultipartUploads",
      "s3:GetBucketVersioning",
      "s3:PutBucketVersioning"
    ]
    resources = [
      module.cidb_s3_bucket.s3_bucket.arn
    ]
  }
  statement {
    sid    = "AWSBucketDelivery-2"
    effect = "Allow"
    principals {
      identifiers = [
        aws_iam_role.cidb-replication-role-tf.arn,
        data.aws_iam_role.ev_config_service_role.arn,
        aws_iam_role.ev_ms_cidb_ami_inventory_role.arn,
        local.engineer_role_arn
      ]
      type = "AWS"
    }
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
      "s3:ReplicateObject",
      "s3:ReplicateDelete",
      "s3:ObjectOwnerOverrideToBucketOwner",
      "s3:PutObjectACL"
    ]
    resources = [
      "${module.cidb_s3_bucket.s3_bucket.arn}/*"
    ]
  }
}

resource "aws_s3_bucket_policy" "cidb_source_bucket_policy" {
  bucket = module.cidb_s3_bucket.s3_bucket.id
  policy = data.aws_iam_policy_document.cidb_ev_source_bucket_policy.json
}

resource "aws_s3_bucket_replication_configuration" "cidb_s3_replication" {
  # count = var.short_env == "prod" ? 1 : 0
  provider = aws.use1

  role   = aws_iam_role.cidb-replication-role-tf.arn
  bucket = module.cidb_s3_bucket.s3_bucket.id

  rule {
    id = "ev_ms_cidb_replication_rule"

    status = "Enabled"

    destination {
      bucket        = var.dest_bucket_arn
      storage_class = "STANDARD"
      encryption_configuration {
        replica_kms_key_id = var.dest_bucket_kms_arn
      }
      access_control_translation {
        owner = "Destination"
      }
      account = var.dest_account_num
      # metrics {
      #   event_threshold {
      #     minutes = 15
      #   }
      #   status = "Enabled"
      # }
      # replication_time {
      #   status = "Enabled"
      #   time {
      #     minutes = 15
      #   }
      # }

    }
    source_selection_criteria {
      sse_kms_encrypted_objects {
        status = "Enabled"
      }
    }
  }
}
