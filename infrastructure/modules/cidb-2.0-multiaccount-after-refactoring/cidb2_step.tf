# CloudWatch Log Group for Step Function logs
resource "aws_cloudwatch_log_group" "sfn_log_group" {
  name_prefix       = "/aws/vendedlogs/states/cidb2_step_functions-"
  retention_in_days = 14
  
  # Best practice: Encrypt logs
  kms_key_id = var.logs_kms_key_arn
  
  tags = {
    Environment = var.environment
    Service     = "cidb2"
    Component   = "step-functions"
  }
}

#-------------------------------------------------------------------
# State Machine for lambda parallel execution
#-------------------------------------------------------------------
resource "aws_sfn_state_machine" "cidb2_step_functions" {
  name     = "${var.short_env}-cidb2-step-function"
  role_arn = aws_iam_role.step_function_role.arn
  
  definition = templatefile("${path.module}/statemachine/statemachine.asl.json", {
    # Core collectors
    lambda_IAM = module.lambda_collector["IAM"].lambda_function_arn
    lambda_KMS = module.lambda_collector["KMS"].lambda_function_arn
    lambda_EC2 = module.lambda_collector["EC2"].lambda_function_arn
    lambda_S3  = module.lambda_collector["S3"].lambda_function_arn
    
    # Results processor Lambda
    lambda_results_processor = aws_lambda_function.results_processor.arn
  })
  
  logging_configuration {
    level           = "ALL"
    log_destination = "${aws_cloudwatch_log_group.sfn_log_group.arn}:*"
    include_execution_data = true
  }

  tracing_configuration {
    enabled = true
  }
  
  tags = {
    Environment = var.environment
    Service     = "cidb2"
    Component   = "orchestration"
  }
}

# Schedule to trigger the Step Function daily
resource "aws_scheduler_schedule" "trigger_inventory" {
  name        = "${var.short_env}-cidb2-trigger-inventory"
  description = "Daily trigger for CIDB2 multi-account inventory collection"
  
  flexible_time_window {
    mode = "OFF"
  }
  
  # Can be customized with a variable
  schedule_expression = var.inventory_schedule_expression

  target {
    arn      = aws_sfn_state_machine.cidb2_step_functions.arn
    role_arn = aws_iam_role.eventbridge_stepfunctions_role.arn

    input = jsonencode({
      accounts = var.target_accounts
      config = {
        batch_size = var.default_batch_size
        large_batch_size = var.large_batch_size
        large_batch_threshold = var.large_batch_threshold
        sns_topic_arn = module.cidb2_inventory_sns_topic.sns_topic_arn
      }
    })
  }
}

# Results processor Lambda
resource "aws_lambda_function" "results_processor" {
  function_name    = "${var.short_env}-cidb2-results-processor"
  description      = "Processes and summarizes results from parallel collector lambdas"
  role             = aws_iam_role.results_processor_role.arn
  runtime          = "python3.9"
  handler          = "results_processor.lambda_handler"
  timeout          = 60
  memory_size      = 256
  
  filename         = data.archive_file.results_processor_zip.output_path
  source_code_hash = data.archive_file.results_processor_zip.output_base64sha256
  
  environment {
    variables = {
      LOG_LEVEL     = var.log_level
      SNS_TOPIC_ARN = module.cidb2_inventory_sns_topic.sns_topic_arn
    }
  }
  
  tracing_config {
    mode = "Active"
  }
}

# Package the results processor code
data "archive_file" "results_processor_zip" {
  type        = "zip"
  output_path = "${path.module}/lambda_zip/results_processor.zip"
  
  source_dir  = "${path.module}/src/results_processor"
  
  excludes    = ["__pycache__", "*.pyc"]
}

# IAM Role for the results processor
resource "aws_iam_role" "results_processor_role" {
  name = "${var.short_env}-cidb2-results-processor-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Effect = "Allow"
      }
    ]
  })
  
  # Attach policies for logging, SNS publishing, etc.
  managed_policy_arns = [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  ]
  
  inline_policy {
    name = "sns-publishing"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Action   = ["sns:Publish"]
          Resource = [module.cidb2_inventory_sns_topic.sns_topic_arn]
          Effect   = "Allow"
        }
      ]
    })
  }
}
