

# TODO: 
# - Review log retention policy
# - Logs encryption
# - Review path prefix and pass dynamic values
resource "aws_cloudwatch_log_group" "sfn_log_group" {
  name_prefix       = "/aws/vendedlogs/states/cidb2_step_functions-"
  retention_in_days = 14
}
#-------------------------------------------------------------------
# State Machine for lambda parallel execution
#-------------------------------------------------------------------
# TODO: Manage template and lambda arn with dynamic functions
resource "aws_sfn_state_machine" "cidb2_step_functions" {
  name     = "${var.short_env}-cidb2-step-function"
  role_arn = aws_iam_role.step_function_role.arn
  definition = templatefile("${path.module}/statemachine/statemachine.asl.json", {
    EvCIDB2_CWA        = module.lambda_collector["cloudwatch-appconfig_1"].lambda_function_arn
    EvCIDB2_EC2        = module.lambda_collector["ec2-cassandra_1"].lambda_function_arn
    EvCIDB2_EVR        = module.lambda_collector["events-route53_1"].lambda_function_arn
    EvCIDB2_IAM_Policy = module.lambda_collector["iam-policy"].lambda_function_arn
    lambda_CWA         = module.lambda_collector["cloudwatch-appconfig_0"].lambda_function_arn
    lambda_EC2         = module.lambda_collector["ec2-cassandra_0"].lambda_function_arn
    lambda_EVR         = module.lambda_collector["events-route53_0"].lambda_function_arn
    lambda_merge       = module.lambda_merge.lambda_function_arn
    lambda_Rebalance   = module.lambda_collector["rebalance"].lambda_function_arn
  })
  logging_configuration {
    # TODO: Change in prod
    level           = "ALL"
    log_destination = "${aws_cloudwatch_log_group.sfn_log_group.arn}:*"
  }

}

resource "aws_scheduler_schedule" "trigger_inventory" {
  name = "cidb2_trigger_inventory"
  flexible_time_window {
    mode = "OFF"
  }
  schedule_expression = "cron(0 4 * * ? *)"



  target {
    arn      = aws_sfn_state_machine.cidb2_step_functions.arn
    role_arn = aws_iam_role.eventbridge_stepfunctions_role.arn

    input = jsonencode({
      Payload = var.service_by_category
    })
  }
}