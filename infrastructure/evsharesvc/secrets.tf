resource "aws_secretsmanager_secret" "cidb_key_secret" {
  name        = "/${var.short_env}/passwords/cidb-source"
  description = "sse kms key for cidb bucket"
  kms_key_id  = aws_kms_key.cidb_bucket_key.key_id
  tags = {
    Name = "/${var.short_env}/passwords/cidb-source"
  }
}

resource "aws_secretsmanager_secret_policy" "cidb_key_secret" {
  secret_arn = aws_secretsmanager_secret.cidb_key_secret.arn
  policy     = data.aws_iam_policy_document.cidb_key_creds.json
}