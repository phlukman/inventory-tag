#TODO: Check module to allow to be triggered by SQS
module "lambda_reporter" {

  source        = "terraform-aws-modules/lambda/aws"
  version       = "5.3.0"
  function_name = "${var.short_env}-cidb2-reporter"
  description   = "Lambda function to get tags from SQS queue and generate a custom report "
  handler       = "main.lambda_handler"
  runtime       = "python3.10"
  publish       = true
  timeout       = "300"
  memory_size   = "512"
  source_path   = "${path.module}/cidb2/lambda_reporter"
  create_role   = false
  lambda_role   = aws_iam_role.ev_ms_cidb_ami_inventory_role.arn
  environment_variables = {
    LAMBDA_ACCOUNT  = local.account_alias
    MEMBER_ACCOUNTS = jsonencode(local.member_account_ids)
    SQS_ARN         = module.cidb2_sqs_queue.arn
  }

}

resource "aws_lambda_event_source_mapping" "event_trigger" {
  event_source_arn = module.cidb2_sqs_queue.arn
  enabled          = true
  function_name    = module.lambda_reporter.lambda_function_arn
  batch_size       = 1
}
