variable "region" {}
variable "short_env" {}
# variable "account_alias" {}
variable "tags" {
  default = {}
  type    = map(string)
}
variable "bucket_alias" {}
# variable "account_id" {}
variable "dest_bucket_arn" {}
variable "dest_bucket_kms_arn" {}
variable "fin_billing_env" {}
variable "dest_account_num" {}
