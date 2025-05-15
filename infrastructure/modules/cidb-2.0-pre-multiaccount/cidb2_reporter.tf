#TODO: Check module to allow to be triggered by SQS
module "lambda_reporter" {

  source        = "terraform-aws-modules/lambda/aws"
  version       = "5.3.0"
  function_name = "${var.short_env}-cidb2-reporter"
  description   = "Lambda function to get tags from SQS queue and generate a custom report "
  handler       = "main.lambda_handler"
  runtime       = "python3.10"
  # PERFORMANCE IMPROVEMENT: Increased timeout and memory for processing large volumes
  timeout       = "900"   # Increased from 20 to 900 seconds (15 minutes)
  memory_size   = "1024"  # Increased from 512MB to 1024MB
  source_path = [
    {
      path = "${path.module}/src/cidb2_reporter/"
      pattern = [
        "!test/",
      ]
  }]
  create_role = false
  lambda_role =  aws_iam_role.ev_ms_cidb2_inventory_role.arn
  environment_variables = {
    SQS_ARN = module.cidb2_sqs_queue.arn
    BUCKET_NAME = aws_s3_bucket.cidb2_s3_bucket.id
    # S3 Locking mechanism configuration
    LOCK_TIMEOUT_SECONDS = "60"
    LOCK_MAX_ATTEMPTS = "5"
    LOCK_BASE_BACKOFF_SECONDS = "2.0"
    LOCK_JITTER_FACTOR = "1.0"
  }
}

resource "aws_lambda_event_source_mapping" "event_trigger" {
  event_source_arn = module.cidb2_sqs_queue.arn
  enabled          = true
  function_name    = module.lambda_reporter.lambda_function_arn
  # PERFORMANCE IMPROVEMENT: Increased batch size and added batching window
  batch_size       = 25     # Increased from 1 to 25 for better throughput
  maximum_batching_window_in_seconds = 30  # Added batching window to collect more messages
}
