#------------------------------------------------------------------------------#
# SQS Queue and DLQ queue                                                      #
#------------------------------------------------------------------------------#
module "cidb2_sqs_queue" {
  source = "github.com/Eaton-Vance-Corp/terraform-aws-sqs-queue?ref=v1.0.1"
  name   = "${var.short_env}-cidb2-sqs-queue"
  redrive_policy = jsonencode(
    {
      deadLetterTargetArn = aws_sqs_queue.dlq.arn
      maxReceiveCount     = 2
  })

}

resource "aws_sqs_queue" "dlq" {
  name = "${var.short_env}-cidb2-sqs-dlq"

}



resource "aws_sqs_queue_policy" "cidb2_queue_policy" {
  queue_url = module.cidb2_sqs_queue.id

  policy = <<EOF
  {
    "Version": "2012-10-17",
    "Id": "sqs-policy",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "AWS": "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        },
        "Action": [
          "SQS:SendMessage",
          "SQS:ReceiveMessage"
        ],
        "Resource": "${module.cidb2_sqs_queue.arn}"
      }
    ]
  }
  EOF

}

#-----------------------------------------------------------------------#
# Lambda Producer functions                                            #
#-----------------------------------------------------------------------#

module "lambda_collector" {
  for_each      = local.service_by_category
  source        = "terraform-aws-modules/lambda/aws"
  version       = "5.3.0"
  function_name = "${var.short_env}-cidb2-collector-${each.key}"
  description   = "Lambda function to get tags from a service list"
  handler       = "main.lambda_handler"
  runtime       = "python3.10"
  publish       = true
  timeout       = "300"
  memory_size   = "512"
  source_path   = "${path.module}/cidb2/lambda_collector"
  create_role   = false
  lambda_role   = aws_iam_role.ev_ms_cidb_ami_inventory_role.arn
  environment_variables = {
    LAMBDA_ACCOUNT  = local.account_alias
    MEMBER_ACCOUNTS = jsonencode(local.member_account_ids)
    SNS_TOPIC_ARN   = module.cidb_ami_sns_topic.sns_topic.arn
  }

}


#-----------------------------------------------------------------------#
# SNS Topic for Lambda function to publish to                           #
#-----------------------------------------------------------------------#
#TODO: No tags
module "cidb2_inventory_sns_topic" {
  source          = "github.com/Eaton-Vance-Corp/terraform-aws-sns-topic?ref=v3.1.0"
  sns_topic_name  = "${var.short_env}-cidb2-lambda-collector-sns-topic"
  sns_policy_json = data.aws_iam_policy_document.cidb_sns_policy_json.json
  sns_kms_key_arn = aws_kms_key.sns_kms_key.arn

}

data "aws_iam_policy_document" "lambda_sns_publish_policy_doc" {
  statement {
    effect = "Allow"

    actions = [
      "sns:Publish"
    ]

    resources = [
      module.cidb2_inventory_sns_topic.sns_topic.arn
    ]
    principals {
      type        = "service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}
#--------------------------------------------------------------#
# SNS Topic Subscription to SQS                                #
#--------------------------------------------------------------# 
#TODO: No tags 
module "sns_topic_subscription_sns_to_sqs" {
  source        = "github.com/Eaton-Vance-Corp/terraform-aws-sns-topic?ref=v3.1.0/subscription"
  endpoint      = module.cidb2_sqs_queue.arn
  protocol      = "sqs"
  sns_topic_arn = module.cidb2_inventory_sns_topic.sns_topic.arn

}