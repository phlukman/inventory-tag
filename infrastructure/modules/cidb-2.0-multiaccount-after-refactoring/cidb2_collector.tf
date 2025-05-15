# Dynamic Lambda creation for different service collectors
locals {
  service_collectors = {
    IAM = {
      description   = "Collects IAM policies across multiple accounts"
      memory_size   = 512
      timeout       = 300
      # Higher memory as IAM policy collections can be large
    },
    KMS = {
      description   = "Collects KMS keys across multiple accounts"
      memory_size   = 256
      timeout       = 180
    },
    EC2 = {
      description   = "Collects EC2 inventory across multiple accounts"
      memory_size   = 384
      timeout       = 240
    },
    S3 = {
      description   = "Collects S3 bucket policies across multiple accounts"
      memory_size   = 384
      timeout       = 240
    }
  }
}

# Lambda module for service-specific collectors
module "lambda_collector" {
  for_each = local.service_collectors
  
  source = "../lambda-module" # Adjust path as needed
  
  function_name = "${var.short_env}-cidb2-${lower(each.key)}-collector"
  description   = each.value.description
  handler       = "main.lambda_handler"
  runtime       = "python3.9"
  timeout       = each.value.timeout
  memory_size   = each.value.memory_size
  
  source_path = "${path.module}/src/cidb2_producer"
  
  environment_variables = {
    LOG_LEVEL            = var.log_level
    SNS_TOPIC_ARN        = module.cidb2_inventory_sns_topic.sns_topic_arn
    SERVICE_TYPE         = each.key
    DEFAULT_BATCH_SIZE   = var.default_batch_size
    LARGE_BATCH_SIZE     = var.large_batch_size
    LARGE_BATCH_THRESHOLD = var.large_batch_threshold
  }

  attach_policy_statements = true
  policy_statements = {
    sns = {
      effect    = "Allow",
      actions   = ["sns:Publish"],
      resources = [module.cidb2_inventory_sns_topic.sns_topic_arn]
    },
    assume_role = {
      effect    = "Allow",
      actions   = ["sts:AssumeRole"],
      resources = ["arn:aws:iam::*:role/${var.collector_role_name}"]
    },
    xray = {
      effect    = "Allow",
      actions   = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
        "xray:GetSamplingRules",
        "xray:GetSamplingTargets",
        "xray:GetSamplingStatisticSummaries"
      ],
      resources = ["*"]
    }
  }

  tracing_config_mode = "Active"

  tags = {
    Environment = var.environment
    Service     = "cidb2"
    Component   = "collector-${lower(each.key)}"
  }
}

# SNS Topic for inventory data
module "cidb2_inventory_sns_topic" {
  source = "../sns-topic"
  
  name        = "${var.short_env}-cidb2-inventory"
  fifo_topic  = false # Standard SNS topic for better throughput
  
  # Apply server-side encryption for security
  content_based_deduplication = false
  delivery_policy = jsonencode({
    "http" : {
      "defaultHealthyRetryPolicy" : {
        "numRetries" : 5,
        "numNoDelayRetries" : 2,
        "minDelayTarget" : 1,
        "maxDelayTarget" : 60,
        "numMinDelayRetries" : 3,
        "numMaxDelayRetries" : 0,
        "backoffFunction" : "exponential"
      },
      "disableSubscriptionOverrides" : false
    }
  })
  
  # Create an SQS queue subscription for the reporter Lambda
  create_subscription = true
  protocol            = "sqs"
  endpoint            = module.cidb2_inventory_queue.sqs_queue_arn
  
  tags = {
    Environment = var.environment
    Service     = "cidb2"
    Component   = "inventory-topic"
  }
}

# SQS Queue for inventory data
module "cidb2_inventory_queue" {
  source = "../sqs-queue"
  
  name                      = "${var.short_env}-cidb2-inventory-queue"
  message_retention_seconds = 1209600 # 14 days
  visibility_timeout_seconds = 900    # 15 minutes
  delay_seconds              = 0      # No delay
  
  # Set reasonable limits for the queue
  max_message_size          = 256000  # 256 KB
  receive_wait_time_seconds = 0       # No long polling
  
  # Apply server-side encryption
  sqs_managed_sse_enabled = true
  
  # Allow SNS to send messages to this queue
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "sns.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = "arn:aws:sqs:${var.aws_region}:${var.aws_account_id}:${var.short_env}-cidb2-inventory-queue"
        Condition = {
          ArnEquals = { "aws:SourceArn" = module.cidb2_inventory_sns_topic.sns_topic_arn }
        }
      }
    ]
  })
  
  tags = {
    Environment = var.environment
    Service     = "cidb2"
    Component   = "inventory-queue"
  }
}
