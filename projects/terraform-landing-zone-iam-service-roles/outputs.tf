output "vpc_flow_log_service_role" {
  value = aws_iam_role.ev_vpc_flow_log_service_role
}

output "ev_limited_access_policy" {
  value = aws_iam_policy.ev_limited_access_policy
}

output "config_service_role" {
  value = aws_iam_role.ev_config_service
}

# Current account IAM policy inventory outputs
output "iam_policy_inventory_role" {
  description = "The IAM role that allows inventory of IAM policies in the current account"
  value       = try(aws_iam_role.ev_iam_policy_inventory[0], null)
}

output "iam_policy_inventory_policy" {
  description = "The IAM policy that grants permissions to inventory IAM policies"
  value       = aws_iam_policy.ev_iam_policy_inventory
}

output "iam_policy_inventory_role_arn" {
  description = "The ARN of the IAM role that allows inventory of IAM policies in the current account"
  value       = try(aws_iam_role.ev_iam_policy_inventory[0].arn, "")
}

# Information about IAM policy inventory roles across all target accounts
output "iam_policy_inventory_target_accounts" {
  description = "List of target account IDs where the IAM policy inventory role should be deployed"
  value = {
    for env, accounts in var.iam_inventory_accounts :
      env => contains(var.enable_iam_inventory_environments, env) ? accounts : []
  }
}

output "iam_policy_inventory_expected_role_arns" {
  description = "Map of expected IAM policy inventory role ARNs for all target accounts"
  value = {
    for account_id in flatten([
      for env in var.enable_iam_inventory_environments : 
        lookup(var.iam_inventory_accounts, env, [])
    ]) :
      account_id => "arn:aws:iam::${account_id}:role/EvIAMPolicyInventoryMemberAccountRole"
  }
}
