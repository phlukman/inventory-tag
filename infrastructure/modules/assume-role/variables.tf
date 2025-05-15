###############################################
# Variables
###############################################

variable "region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "source_account_id" {
  description = "Source AWS account ID where roles will be created"
  type        = string
}



variable "source_role_name" {
  description = "Name of the role in the source account that will assume roles in target accounts"
  type        = string
  default     = "ResourceReaderSourceRole"
}

# variable "target_accounts" {
#   description = "List of target AWS accounts to create roles in"
#   type = list(object({
#     account_id  = string
#     name        = string # Human-readable name for the account
#     provider    = string # Provider alias for this account
#   }))
# }

# variable "target_role_name" {
#   description = "Name of the role to be created in target accounts"
#   type        = string
#   default     = "ResourceReaderRole"
# }

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {
    goal = "local-dev"
  }
}
