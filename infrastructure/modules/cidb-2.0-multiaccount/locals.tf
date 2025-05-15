# #----------------------------------------------------
# # assume-role module configuration
# #----------------------------------------------------
# locals {
#   target_providers = {
#     for idx, account in var.target_accounts :
#     account.account_id => {
#       account_id = account.account_id
#       name       = account.name
#       provider   = "aws.target_${idx}"
#     }
#   }
# }


# locals {
#   cidb2_s3_bucket = {
#     bucket_name = "${var.short_env}-cidb2-source-bucket-test"
#     region      = var.region
#   }
# engineer_role_arn             = local.account_alias == "evsharesvcnonprod" ? "arn:aws:iam::477591219415:role/Engineer" : local.account_alias == "evsharesvcprod" ? "arn:aws:iam::435574127453:role/Engineer" : ""

# }
