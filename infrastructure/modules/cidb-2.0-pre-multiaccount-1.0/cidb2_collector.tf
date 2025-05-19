#------------------------------------------------------------------------------#
# SQS Queue and DLQ queue                                                      #
#------------------------------------------------------------------------------#
module "cidb2_sqs_queue" {
  # source = "github.com/Eaton-Vance-Corp/terraform-aws-sqs-queue?ref=v1.0.1"
  source = "github.com/Eaton-Vance-Corp/terraform-aws-sqs-queue?ref=IACS-6851"
  name   = "${var.short_env}-cidb2-sqs-queue"
  redrive_policy = jsonencode(
    {
      deadLetterTargetArn = aws_sqs_queue.dlq.arn
      maxReceiveCount     = 2
  })

  iam_policy_statements = [
    {

      Version = "2012-10-17"
      Statement = [
        {
          
          Action    = [
            "SQS:SendMessage",
            "SQS:ReceiveMessage"
          ]
           Condition = {
            "ArnEquals" = {
              "aws:SourceArn" = module.cidb2_inventory_sns_topic.sns_topic.arn
            }
            }
          Effect    = "Allow"
          Principal = {
            Service = "sns.amazonaws.com"
          }
          Resource  = module.cidb2_sqs_queue.arn
        }
      ]
    }
  ]
}


resource "aws_sqs_queue" "dlq" {
  name = "${var.short_env}-cidb2-sqs-dlq"

}

#-----------------------------------------------------------------------#
# Lambda Producer functions                                            #
#-----------------------------------------------------------------------#
#TODO: Create a separate policy
module "lambda_collector" {
  for_each      = var.service_by_category
  source        = "terraform-aws-modules/lambda/aws"
  version       = "5.3.0"
  function_name = "${var.short_env}-cidb2-collector-${each.key}"
  description   = "Lambda function to get tags from a service list"
  handler       = "main.lambda_handler"
  runtime       = "python3.10"
  publish       = true
  # PERFORMANCE IMPROVEMENT: Increased timeout and memory for processing large volumes
  timeout       = "900"   # Increased from 300 to 900 seconds (15 minutes)
  memory_size   = "1024"  # Increased from 512MB to 1024MB
  source_path   = "${path.module}/src/cidb2_producer"
  create_role   = false
  lambda_role   =  aws_iam_role.ev_ms_cidb2_inventory_role.arn
  hash_extra = uuid()
  environment_variables = {
    LAMBDA_ACCOUNT  = var.account_alias
    MEMBER_ACCOUNTS = jsonencode(var.member_accounts_ids)
    SNS_TOPIC_ARN   = module.cidb2_inventory_sns_topic.sns_topic.arn
  }
}


#-----------------------------------------------------------------------#
# SNS Topic for Lambda function to publish to                           #
#-----------------------------------------------------------------------#
#TODO: No tags
module "cidb2_inventory_sns_topic" {
  source          = "github.com/Eaton-Vance-Corp/terraform-aws-sns-topic?ref=v3.1.0"
  sns_topic_name  = "${var.short_env}-cidb2-lambda-collector-sns-topic"
  sns_policy_json = data.aws_iam_policy_document.cidb2_sns_policy_json.json
  sns_kms_key_arn = var.sns_kms_key_arn
}
