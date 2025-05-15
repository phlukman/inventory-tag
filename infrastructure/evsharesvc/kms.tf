# single region key
resource "aws_kms_key" "cidb_bucket_key" {
  description             = "This key is used to encrypt the CIDB bucket"
  deletion_window_in_days = 10
  enable_key_rotation     = true
  multi_region            = false
  policy                  = data.aws_iam_policy_document.cidb_kms_key_policy.json
  tags = {
    Name = "cidb-source-bucket-key"
  }
}

resource "aws_kms_alias" "cidb_bucket_key_alias" {
  name          = "alias/cidb-source-bucket-key"
  target_key_id = aws_kms_key.cidb_bucket_key.key_id
}

# MR key and replicas
resource "aws_kms_key" "cidb_app_source_bucket_key" {
  description             = "This key is used to encrypt the EV CIDB Source Bucket"
  deletion_window_in_days = 10
  enable_key_rotation     = true
  multi_region            = true
  policy                  = data.aws_iam_policy_document.cidb_kms_key_policy.json
  tags = {
    Name = "cidb-app-source-bucket-key"
  }
}

resource "aws_kms_alias" "cidb_app_source_bucket_key" {
  name          = "alias/cidb-app-source-bucket-key"
  target_key_id = aws_kms_key.cidb_app_source_bucket_key.key_id
}


resource "aws_kms_replica_key" "cidb_app_source_bucket_key_use2" {
  description             = "USE2 Replica for cidb app source bucket key in USE1"
  primary_key_arn         = aws_kms_key.cidb_app_source_bucket_key.arn
  policy                  = data.aws_iam_policy_document.cidb_kms_key_policy.json
  provider                = aws.use2
  deletion_window_in_days = 10
  tags = {
    Name = "cidb-app-source-bucket-key-replica-use2"
  }
}

resource "aws_kms_alias" "cidb_app_source_bucket_key_use2" {
  name          = "alias/cidb-app-source-bucket-key-replica-use2"
  target_key_id = aws_kms_replica_key.cidb_app_source_bucket_key_use2.key_id
}

resource "aws_kms_replica_key" "cidb_app_source_bucket_key_usw2" {
  description             = "USW2 Replica for cidb app source bucket key in use1"
  primary_key_arn         = aws_kms_key.cidb_app_source_bucket_key.arn
  policy                  = data.aws_iam_policy_document.cidb_kms_key_policy.json
  provider                = aws.usw2
  deletion_window_in_days = 10
  tags = {
    Name = "cidb-app-source-bucket-key-replica-usw2"
  }
}

resource "aws_kms_alias" "cidb_app_source_bucket_key_usw2" {
  name          = "alias/cidb-app-source-bucket-key-replica-usw2"
  target_key_id = aws_kms_replica_key.cidb_app_source_bucket_key_usw2.key_id
}
