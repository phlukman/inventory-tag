resource "aws_iam_role" "step_function_role" {
  name               = "${var.short_env}-step-function-role"
  assume_role_policy = data.aws_iam_policy_document.step_function_assume_role_policy.json
}

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

resource "aws_sfn_state_machine" "cidb2_step_functions" {
  name     = "${var.short_env}-cidb2-step-function"
  role_arn = aws_iam_role.step_function_role.arn
  definition = jsonencode({
  })
}