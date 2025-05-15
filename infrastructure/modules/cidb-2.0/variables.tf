variable "short_env" {
  description = ""
  type        = string
}

variable "service_by_category" {
  description = "Categories of AWS services that are not collected properly by AWS Config"
  type        = map(list(string))
}

variable "current_account_id" {
  description = "AWS account id where the CIDB infra will be hosted"
  type        = string
}

variable "sns_topic_arn" {
  description = ""
  type        = string
}

variable "account_alias" {
  description = ""
  type        = string
}

variable "member_accounts_ids" {
  description = "JSON-encoded list of member account IDs"
  type        = list(string)

}

variable "cidb_sns_policy_json" {
  description = "JSON-formatted IAM policy document for SNS"
  type        = string

  validation {
    condition     = can(jsondecode(var.cidb_sns_policy_json))
    error_message = "The sns_policy_json value must be a valid JSON string."
  }
}

variable "s3_bucket_arn" {
  description = "S3 bucket ARN where the CIDB data will be stored"
  type        = string
}


variable "sns_kms_key_arn" {
  description = "SNS encryption key arn"
  type        = string
}

variable "cidb_app_source_bucket_key_arn" {
  description = "S3 encryption key"
  type = string
}
