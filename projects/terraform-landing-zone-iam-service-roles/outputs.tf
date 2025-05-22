output "vpc_flow_log_service_role" {
  value = aws_iam_role.ev_vpc_flow_log_service_role
}

output "ev_limited_access_policy" {
  value = aws_iam_policy.ev_limited_access_policy
}

output "config_service_role" {
  value = aws_iam_role.ev_config_service
}
