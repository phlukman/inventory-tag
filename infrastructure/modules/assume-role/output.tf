###############################################
# Outputs
###############################################

output "source_role_arn" {
  description = "ARN of the source account role for local dev. It is not the role to be used by the Lambda producers"
  value       = aws_iam_role.source_role_local_dev.arn
}

# output "target_role_arns" {
#   description = "ARNs of the target account roles"
#   value = {
#     for account_id, role in aws_iam_role.target_role :
#     account_id => role.arn
#   }
# }

# output "target_role_policy_document" {
#   description = "Policy document for the target role (to be created in target accounts manually)"
#   value       = local.target_role_policy_document
# }

# output "target_role_trust_policy" {
#   description = "Trust policy for the target role (to be created in target accounts manually)"
#   value       = local.target_role_trust_policy
# }