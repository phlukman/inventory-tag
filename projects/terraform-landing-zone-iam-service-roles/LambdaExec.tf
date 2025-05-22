data "aws_iam_policy_document" "ev_lambda_exec" {
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

resource "aws_iam_role" "ev_lambda_exec" {
  name               = "LambdaExec"
  assume_role_policy = data.aws_iam_policy_document.ev_lambda_exec.json
  path               = "/"
  tags = merge(var.tags, {
    "Name" = "LambdaExec"
  })
}

resource "aws_iam_role_policy_attachment" "AmazonEC2ReadOnlyAccess_lambdaexec_policy_attachment" {
  role       = aws_iam_role.ev_lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "AmazonSNSRole_lambdaexec_policy_attachment" {
  role       = aws_iam_role.ev_lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonSNSRole"
}
