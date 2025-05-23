variable "account_alias" {}
variable "account_id" {}
variable "tags" {
  type    = map(string)
  default = null
}

# IAM Policy Inventory Target Accounts
variable "iam_inventory_accounts" {
  description = "Map of environment types to lists of AWS account IDs where the IAM policy inventory role will be deployed"
  type        = map(list(string))
  default     = {
    sandbox = [
      "992854303108", # calresearchsandbox
      "053210025230", # evcesandbox
      "175316323768", # evgigssandbox
      "168002464918", # evinfrasandbox
      "984670241748", # evinvesttechsandbox
      "829689304269", # evitrisksandbox
      "119173687103", # evsalesdistsandbox
      "286174197317", # ppacitizendevelopersandbox
      "511182126229", # ppacoresoftsvssandbox
      "453170101838", # ppadatamgtsandbox
      "362895556546", # ppaeicasandbox
      "767397819526", # ppagenaisandbox
      "658302302575", # ppainvestsyssandbox
      "131696788323"  # pparesearchsandbox
    ],
    dev     = [],  # To be populated with dev account IDs
    staging = [],  # To be populated with staging account IDs
    prod    = []   # To be populated with production account IDs
  }
}

# IAM Policy Inventory Lambda Role ARN
variable "cidb_collector_lambda_role_arn" {
  description = "ARN of the Lambda execution role that will assume the IAM Policy Inventory role"
  type        = string
  default     = "arn:aws:iam::477591219415:role/ev_ms_cidb2_lambda_execute_role"
}

# Environments to enable IAM policy inventory for
variable "enable_iam_inventory_environments" {
  description = "List of environments to enable IAM policy inventory for"
  type        = list(string)
  default     = ["sandbox"]  # By default only enable for sandbox
}
