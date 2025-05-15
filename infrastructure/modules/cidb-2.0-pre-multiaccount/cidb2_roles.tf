#-----------------------------------------------------
# This file contains the IAM roles and policies for the CIDB 2.0 module.
#-----------------------------------------------------
#-----------------------------------------------------------
# Step Function Logging policy
#-----------------------------------------------------------

data "aws_iam_policy_document" "step_function_assume_role_policy" {
  version = "2012-10-17"

  statement {
    effect = "Allow"

    actions = [
      "sts:AssumeRole"
    ]

    principals {
      type = "Service"
      identifiers = [
        "states.amazonaws.com"
      ]
    }
  }
}

resource "aws_iam_policy" "state_machine_log_delivery_policy" {
  name        = "${var.short_env}-cidb2-state-machine-log-delivery-policy"
  description = "Policy to allow Step Function to write logs to CloudWatch"
  policy = <<EOF
{
  "Version" : "2012-10-17",
  "Statement" : [
    {
      "Effect" : "Allow",
      "Action" : [
        "logs:CreateLogDelivery",
        "logs:GetLogDelivery",
        "logs:UpdateLogDelivery",
        "logs:DeleteLogDelivery",
        "logs:ListLogDeliveries",
        "logs:PutResourcePolicy",
        "logs:DescribeResourcePolicies",
        "logs:DescribeLogGroups"
      ],
      "Resource" : "*"
    }
  ]
}
EOF
}

resource "aws_iam_role" "step_function_role" {
  name               = "${var.short_env}-step-function-role"
  assume_role_policy = data.aws_iam_policy_document.step_function_assume_role_policy.json
}

resource "aws_iam_role_policy_attachment" "state_machine_log_delivery_policy_attachment" {
  role       = aws_iam_role.step_function_role.name
  policy_arn = aws_iam_policy.state_machine_log_delivery_policy.arn
}

#------------------------------------------------------------

resource "aws_cloudwatch_log_resource_policy" "step_function_log_policy" {
  policy_name = "${var.short_env}-cidb2-step_function_log_policy"
  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Action = [
          "logs:CreateLogsStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.sfn_log_group.arn}:*"
      }
    ]
  })
}

data "aws_iam_policy_document" "step_function_invoke_lambda_policy_document" {
  statement {
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction"
    ]

    resources = [
      module.lambda_collector["IAM"].lambda_function_arn,
      module.lambda_collector["KMS"].lambda_function_arn
    ]
  }
}

resource "aws_iam_policy" "step_function_invoke_lambda_policy" {
  name        = "${var.short_env}-step-function-invoke-lambda-policy"
  description = "Policy to allow Step Function to invoke Lambda functions"
  policy      = data.aws_iam_policy_document.step_function_invoke_lambda_policy_document.json
}

resource "aws_iam_role_policy_attachment" "step_function_invoke_lambda_policy_attachment" {
  role       = aws_iam_role.step_function_role.name
  policy_arn = aws_iam_policy.step_function_invoke_lambda_policy.arn
}


resource "aws_iam_role_policy" "lambda_sns_policy" {
  name = "${var.short_env}-lambda_sns_policy"
  #  role = aws_iam_role.lambda_execution.id
  role = aws_iam_role.ev_ms_cidb2_inventory_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = module.cidb2_inventory_sns_topic.sns_topic.arn
      }
    ]
  })
}


#------------------------------------------------------------------
# EventBridge assume role 
#-----------------------------------------------------------------

data "aws_iam_policy_document" "eventbridge_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = [
        "events.amazonaws.com",
        "scheduler.amazonaws.com"
        ]
    }
  }
}

resource "aws_iam_policy" "eventbridge_access_policy" {
  description = "Policy for EventBridge Scheduler to trigger Step Function"
  name        = "${var.short_env}-eventbridge_access_policy"
  policy = jsonencode(
    {
      Version = "2012-10-17"
      Statement = [
        {
          Action = [
            "states:StartExecution"
          ],
          Effect   = "Allow"
          Resource = aws_sfn_state_machine.cidb2_step_functions.arn
        }
      ]
    }
  )
}

resource "aws_iam_role" "eventbridge_stepfunctions_role" {
  name               = "eventbridge_stepfunctions_role"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_policy.json
}


resource "aws_iam_role_policy_attachment" "eventbridge_access_policy_attachment" {
  role       = aws_iam_role.eventbridge_stepfunctions_role.name
  policy_arn = aws_iam_policy.eventbridge_access_policy.arn
}



#---------------------------------------------------------------------------------------
# Lambda producer role policy
#---------------------------------------------------------------------------------------
resource "aws_iam_role" "ev_ms_cidb2_inventory_role" {
  name = "ev_ms_cidb2_lambda_execute_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
    }
  )
  tags = {
    Name = "EvMSCIDBAMIInventorySharedSvcLambdaExecRole"
  }
}

resource "aws_iam_role_policy" "ami_lambda_exec_role_policy" {
  name = "${var.short_env}-ev_cidb2_inventory_lambda_exec_role_policy"
  role = aws_iam_role.ev_ms_cidb2_inventory_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Added s3:DeleteObject permission for S3 locking mechanism
        Action   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:DeleteObject"],
        Effect   = "Allow",
        Resource = [var.s3_bucket_arn, "${var.s3_bucket_arn}/*"]
      },
      {
        Action   = ["kms:Encrypt", "kms:GenerateDataKey"],
        Effect   = "Allow",
        Resource = [var.cidb_app_source_bucket_key_arn]
      },
      {
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"],
        Effect   = "Allow",
        Resource = [var.sns_kms_key_arn]
      },
      {
        Action = ["sts:AssumeRole"],
        Effect = "Allow",
        Resource = [
          for account in var.member_accounts_ids : "arn:aws:iam::${account}:role/EvMSCIDBAMIInventoryMemberAccountRole"
        ]
      },
      {
        
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ],
        Effect = "Allow",
        Resource = [ module.cidb2_sqs_queue.arn]
      },
      {
        Action   = [
          "sns:Publish"
        ],
        Effect   = "Allow",
        Resource = [
          var.sns_topic_arn,
          module.cidb2_inventory_sns_topic.sns_topic.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "AWSLambdaBasicExecutionRolePolicy" {
  role       = aws_iam_role.ev_ms_cidb2_inventory_role.id
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# resource "aws_iam_role_policy_attachment" "cidb_allow_sts_assume_role" {
#   role       = aws_iam_role.ev_ms_cidb2_inventory_role.id
#   policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaKMSPolicy"
# }

#-----------------------------------------------------------------------------------------
# CIDB2 SNS Policy
#------------------------------------------------------------------------------------------
data "aws_iam_policy_document" "cidb2_sns_policy_json" {
  version   = "2012-10-17"
  policy_id = "cidb2_sns-topic-policy"

  statement {
    principals {
      type        = "Service"
      identifiers = ["sqs.amazonaws.com"]
    }
    actions = [
      "SNS:Subscribe",
      "SNS:SetTopicAttributes",
      "SNS:RemovePermission",
      "SNS:Receive",
      "SNS:Publish",
      "SNS:ListSubscriptionsByTopic",
      "SNS:GetTopicAttributes",
      "SNS:DeleteTopic",
      "SNS:AddPermission",
    ]
    effect    = "Allow"
    resources = ["*"]
  }
  statement {
    sid = "Allow lambda to publish to sns"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = [
      "SNS:Publish"
    ]
    effect    = "Allow"
    resources = [module.cidb2_inventory_sns_topic.sns_topic.arn]
  }

}


#---------------------------------------------------------------------
# Allow IAM Lambda to assume target account roles
#---------------------------------------------------------------------
data aws_iam_policy_document "allow_lambda_remote_account_access"{
  statement {
    effect = "Allow"
    actions = ["sts:AssumeRole"]
    resources = [
      "arn:aws:iam::053210025230:role/cidb-inventory-role"
    ]
  }
}

resource "aws_iam_role_policy" "assume_remote_role_policy" {
  name   = "cidb2-assume-remote-role-policy"
  role   = aws_iam_role.ev_ms_cidb2_inventory_role.id
  policy = data.aws_iam_policy_document.allow_lambda_remote_account_access.json
}
