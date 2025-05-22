data "aws_iam_policy_document" "ev_staax" {
  version = "2012-10-17"
  statement {
    actions = [
                "config:SelectResourceConfig",
              ]
    effect    = "Allow"
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ev_staax" {
  name        = "EvStaaxPolicy"
  path        = "/"
  description = "Permissions required to list describe services and query AWS config"
  policy      = data.aws_iam_policy_document.ev_staax.json
}

data "aws_iam_policy_document" "ev_staax_exec" {
  version = "2012-10-17"
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = local.staax_lambda_exec_role_arns
      type        = "AWS"
    }
    effect = "Allow"
  }
}

resource "aws_iam_role" "ev_staax" {
  count = local.enable_sandbox ? 1 : 0
  name               = "EvStaaxMemberAccountRole"
  path               = "/"
  assume_role_policy = data.aws_iam_policy_document.ev_staax_exec.json
  tags = merge(var.tags, {
    Name = "EvMSStaaxMemberAccountRole"
  })
}

resource "aws_iam_role_policy_attachment" "ev_staax" {
  count      = local.enable_sandbox ? 1 : 0
  role       = aws_iam_role.ev_staax[0].name
  policy_arn = aws_iam_policy.ev_staax.arn
}

resource "aws_iam_role_policy_attachment" "ev_staax_readonly" {
  count      = local.enable_sandbox ? 1 : 0
  role       = aws_iam_role.ev_staax[0].name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}






