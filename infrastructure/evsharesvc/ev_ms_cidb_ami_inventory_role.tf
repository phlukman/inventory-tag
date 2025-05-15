resource "aws_iam_role" "ev_ms_cidb_ami_inventory_role" {
  name = "EvMSCIDBAMIInventorySharedSvcLambdaExecRole"
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
  name = "ev_ms_cidb_ami_inventory_lambda_exec_role_policy"
  role = aws_iam_role.ev_ms_cidb_ami_inventory_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
        Effect   = "Allow",
        Resource = [module.cidb_s3_bucket.s3_bucket.arn, "${module.cidb_s3_bucket.s3_bucket.arn}/*"]
      },
      {
        Action   = ["kms:Encrypt", "kms:GenerateDataKey"],
        Effect   = "Allow",
        Resource = [aws_kms_key.cidb_app_source_bucket_key.arn]
      },
      {
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"],
        Effect   = "Allow",
        Resource = [aws_kms_key.sns_kms_key.arn]
      },
      {
        Action = ["sts:AssumeRole"],
        Effect = "Allow",
        Resource = [
          for account in local.member_account_ids : "arn:aws:iam::${account}:role/EvMSCIDBAMIInventoryMemberAccountRole"
        ]
      },
      {
        Action   = ["sns:Publish"],
        Effect   = "Allow",
        Resource = [module.cidb_ami_sns_topic.sns_topic.arn]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "AWSLambdaBasicExecutionRolePolicy" {
  role       = aws_iam_role.ev_ms_cidb_ami_inventory_role.id
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}