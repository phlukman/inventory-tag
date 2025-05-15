module "cidb2-infra" {
  source                         = "../modules/cidb-2.0"
  short_env                      = "dev"
  service_by_category            = local.service_by_category
  current_account_id             = data.aws_caller_identity.current.account_id
  sns_topic_arn                  = module.cidb_ami_sns_topic.sns_topic.arn
  account_alias                  = local.account_alias
  member_accounts_ids            = local.member_account_ids
  cidb_sns_policy_json           = data.aws_iam_policy_document.cidb_sns_policy_json.json
  sns_kms_key_arn                = aws_kms_key.sns_kms_key.arn
  s3_bucket_arn                  = module.cidb_s3_bucket.s3_bucket.arn
  cidb_app_source_bucket_key_arn = aws_kms_key.cidb_app_source_bucket_key.arn
}

module "assume_role_new" {

  source = "../modules/assume-role"
  # short_env = "dev"
  source_account_id = data.aws_caller_identity.current.account_id
  source_role_name  = "CIDB2-Inventory-Role"
  # target_accounts = local.target_accounts
  # target_role_name = "CIDB2-Inventory-Role"
  tags = local.tags

  providers = {
    aws = aws
  }
}

