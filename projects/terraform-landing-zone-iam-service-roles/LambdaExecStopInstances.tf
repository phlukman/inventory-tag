data "aws_iam_policy_document" "ev_lambda_exec_stop_instances" {
  version = "2012-10-17"
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = ["lambda.amazonaws.com"]
      type        = "Service"
    }
    effect = "Allow"
  }
}

resource "aws_iam_role" "ev_lambda_exec_stop_instances" {
  name               = "LambdaExecStopInstances"
  assume_role_policy = data.aws_iam_policy_document.ev_lambda_exec_stop_instances.json
  path               = "/"
  tags = merge(var.tags, {
    "Name" = "LambdaExecStopInstances"
  })
}

resource "aws_iam_role_policy_attachment" "AmazonEC2FullAccess_lambdaexecstopinstances_policy_attachment" {
  role       = aws_iam_role.ev_lambda_exec_stop_instances.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2FullAccess"
}

resource "aws_iam_role_policy_attachment" "AmazonRDSFullAccess_lambdaexecstopinstances_policy_attachment" {
  role       = aws_iam_role.ev_lambda_exec_stop_instances.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonRDSFullAccess"
}

resource "aws_iam_role_policy_attachment" "AmazonSNSRole_lambdaexecstopinstances_policy_attachment" {
  role       = aws_iam_role.ev_lambda_exec_stop_instances.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonSNSRole"
}
