# IAM Role for EventBridge Scheduler execution
resource "aws_iam_role" "scheduler_execution_role" {
  name = "org-accounts-lister-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })
}

# Policy to allow EventBridge Scheduler to invoke Lambda function
resource "aws_iam_policy" "lambda_invoke_policy" {
  name        = "org-accounts-lister-scheduler-policy"
  description = "Allow EventBridge Scheduler to invoke the Organization Accounts Lister Lambda function"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "lambda:InvokeFunction"
        Effect   = "Allow"
        Resource = module.org_accounts_lister_lambda.lambda_function_arn
      },
    ]
  })
}

# Attach the policy to the Scheduler role
resource "aws_iam_role_policy_attachment" "scheduler_lambda_invoke" {
  role       = aws_iam_role.scheduler_execution_role.name
  policy_arn = aws_iam_policy.lambda_invoke_policy.arn
}

# Add lambda permission to allow invocation from EventBridge Scheduler
resource "aws_lambda_permission" "allow_scheduler" {
  statement_id  = "AllowExecutionFromEventBridgeScheduler"
  action        = "lambda:InvokeFunction"
  function_name = module.org_accounts_lister_lambda.lambda_function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.org_accounts_lister_daily_schedule.arn
}

