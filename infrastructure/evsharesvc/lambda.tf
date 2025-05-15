module "ami_lambda" {
  source        = "terraform-aws-modules/lambda/aws"
  version       = "5.3.0"
  function_name = "get-ami-metadata"
  description   = "Lambda function to get ami metadata"
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.10"
  publish       = true
  timeout       = "300"
  memory_size   = "512"
  source_path   = "${path.module}/ami-metadata"
  create_role   = false
  lambda_role   = aws_iam_role.ev_ms_cidb_ami_inventory_role.arn
  environment_variables = {
    LAMBDA_ACCOUNT  = local.account_alias
    MEMBER_ACCOUNTS = jsonencode(local.member_account_ids)
    SNS_TOPIC_ARN   = module.cidb_ami_sns_topic.sns_topic.arn
  }
}

