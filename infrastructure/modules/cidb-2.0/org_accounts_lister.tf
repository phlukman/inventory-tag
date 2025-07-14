module "org_accounts_lister_lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "5.3.0"

  function_name = "org-accounts-reporter"
  description   = "Lambda function to list all AWS organization accounts with role assumption capabilities"
  handler       = "main.lambda_handler"
  runtime       = "python3.10"
  timeout       = "900" # 15 minutes
  memory_size   = "512" # 512MB

  source_path = [
    {
      path = "${path.module}/src/org_accounts_lister/"
      pattern = [
        "!test_locally.py",
        "!__pycache__/",
      ]
    }
  ]

  create_role = false
  lambda_role = aws_iam_role.ev_ms_cidb2_inventory_role.arn

  environment_variables = {
    BUCKET_NAME           = var.s3_bucket_name
    ROLE_TO_ASSUME        = local.app_role
    MANAGEMENT_ACCOUNT_ID = "267821145838"
    MANAGEMENT_ROLE_NAME  = "EVCIDB-Crossaccount-Role"
    ENV_EXCLUDED_ACCOUNTS = jsonencode(local.env_excluded_accounts)
  }
}



# EventBridge Scheduler to trigger the Lambda function daily at 2 AM UTC
resource "aws_scheduler_schedule" "org_accounts_lister_daily_schedule" {
  name        = "org-accounts-lister-daily-schedule"
  description = "Runs the Organization Accounts Lister Lambda function daily at 2 AM UTC"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "cron(0 2 * * ? *)" # Daily at 2 AM UTC (Note: AWS EventBridge uses a six-field cron expression: Minutes Hours Day-of-month Month Day-of-week Year, which differs from standard cron's five fields)

  target {
    arn      = module.org_accounts_lister_lambda.lambda_function_arn
    role_arn = aws_iam_role.scheduler_execution_role.arn

    input = jsonencode({
      "source" : "eventbridge-scheduler",
      "detail-type" : "Scheduled Event",
      "time" : "${formatdate("YYYY-MM-DD", timestamp())}T${formatdate("HH:mm:ss", timestamp())}Z",
      "resources" : ["${module.org_accounts_lister_lambda.lambda_function_arn}"],
      "detail" : {
        "action" : "list_accounts",
        "scheduled" : true
      }
    })
  }
}


# CloudWatch Log Group for EventBridge Scheduler
resource "aws_cloudwatch_log_group" "org_accounts_lister_logs" {
  name              = "/aws/events/org-accounts-lister-schedule"
  retention_in_days = 30

  tags = {
    Environment = var.short_env
    Service     = "org-accounts-lister"
  }
}

