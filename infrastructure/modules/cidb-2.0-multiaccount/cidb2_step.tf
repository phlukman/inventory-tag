

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
     
    lambda_IAM = module.lambda_collector["IAM"].lambda_function_arn
    lambda_KMS = module.lambda_collector["KMS"].lambda_function_arn
  })
  logging_configuration {
    level           = "ALL"
    log_destination = "${aws_cloudwatch_log_group.sfn_log_group.arn}:*"
  }

}

resource "aws_scheduler_schedule" "trigger_inventory" {
  name = "cidb2_trigger_inventory"
  flexible_time_window {
    mode = "OFF"
  }
  schedule_expression = "rate(1 day)"


  target {
    arn      = aws_sfn_state_machine.cidb2_step_functions.arn
    role_arn = aws_iam_role.eventbridge_stepfunctions_role.arn

    input = jsonencode({
      Payload = var.service_by_category
    })
  }
}