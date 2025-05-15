data "aws_caller_identity" "current" {}
data "aws_organizations_organization" "current" {}
data "aws_iam_role" "ev_config_service_role" {
  name = "ConfigService"
}
data "aws_iam_account_alias" "current" {}
