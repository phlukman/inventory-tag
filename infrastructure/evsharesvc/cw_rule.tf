resource "aws_cloudwatch_event_rule" "cidb_ami" {
  name                = "cidb-ami-inventory"
  description         = "Rule to run CIDB AMI Inventory lambda every day at 12 AM"
  schedule_expression = "cron(0 0 * * ? *)"
}

resource "aws_cloudwatch_event_target" "cidb_ami" {
  rule      = aws_cloudwatch_event_rule.cidb_ami.name
  target_id = "lambda"
  arn       = module.ami_lambda.lambda_function_arn
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatchEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = module.ami_lambda.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cidb_ami.arn
}

resource "aws_cloudwatch_metric_alarm" "ami_lambda_invocation_alarm" {
  alarm_name          = "cidb-ami-inventory-lambda-failed-invocation"
  comparison_operator = "LessThanThreshold"
  datapoints_to_alarm = 1
  evaluation_periods  = "1"
  metric_name         = "Invocations"
  namespace           = "AWS/Lambda"
  period              = "86400"
  statistic           = "Sum"
  threshold           = "1"
  treat_missing_data  = "breaching"
  alarm_description   = "Alarm if Lambda function is not invoked at least once in the last 24 hours"
  dimensions = {
    FunctionName = module.ami_lambda.lambda_function_name
  }

  alarm_actions = [module.cidb_ami_sns_topic.sns_topic.arn]
}