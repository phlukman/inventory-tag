output "sqs_queue_arn" {
  description = "The ARN of the primary SQS queue"
  value       = module.cidb2_sqs_queue.arn
}

output "sqs_queue_url" {
  description = "The URL of the primary SQS queue"
  value       = module.cidb2_sqs_queue.id
}

output "sqs_dlq_arn" {
  description = "The ARN of the dead-letter queue (DLQ)"
  value       = aws_sqs_queue.dlq.arn
}

output "sns_topic_arn" {
  description = "The ARN of the SNS topic used by the Lambda collector"
  value       = module.cidb2_inventory_sns_topic.sns_topic.arn
}

output "lambda_collector_arns" {
  description = "The ARNs of all Lambda collector functions"
  value       = values(module.lambda_collector)[*].lambda_function_arn
}

output "lambda_reporter_arn" {
  description = "The ARN of the Lambda reporter function"
  value       = module.lambda_reporter.lambda_function_arn
}

output "lambda_reporter_event_source_mapping_id" {
  description = "The ID of the event source mapping for the Lambda reporter"
  value       = aws_lambda_event_source_mapping.event_trigger.id
}

output "cidb2_lambda_role_arn" {
  description = "The ARN of the IAM role for the Lambda functions"
  value       = aws_iam_role.ev_ms_cidb2_inventory_role.arn
}

# Output to confirm the attachment and show which role ARNs can be assumed
output "lambda_iam_inventory_policy_attached" {
  description = "Confirmation that the IAM Policy Inventory Assumer policy is attached to the Lambda execution role"
  value       = "IAM Policy Inventory Assumer policy attached to ${aws_iam_role.ev_ms_cidb2_inventory_role.name}"
}

output "assumable_iam_policy_inventory_roles" {
  description = "List of IAM policy inventory role ARNs that can be assumed by the Lambda"
  value       = length(var.iam_policy_inventory_role_arns) > 0 ? values(var.iam_policy_inventory_role_arns) : ["Using wildcard pattern: arn:aws:iam::*:role/EvIAMPolicyInventoryMemberAccountRole"]
}