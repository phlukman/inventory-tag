data "aws_iam_policy_document" "ev_ssm_automation_execution_policy" {
  version = "2012-10-17"
  statement {
    effect = "Allow"
    actions = [
      "ec2:DescribeInstanceStatus",
      "ec2:DescribeTags"
    ]
    resources = ["*"]
  }
  statement {
    effect = "Allow"
    actions = [
      "resource-groups:ListGroupResources",
      "tag:GetResources"
    ]
    resources = ["*"]
  }
  statement {
    effect = "Allow"
    actions = [
      "ssm:DescribeInstanceInformation",
      "ssm:GetAutomationExecution",
      "ssm:GetParameters",
      "ssm:ListCommands",
      "ssm:ListCommandInvocations"
    ]
    resources = ["*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ssm:*:*:document/AWS-RunPatchBaseline"]
  }
  statement {
    effect    = "Allow"
    actions   = ["ssm:SendCommand"]
    resources = ["*"]
    condition {
      test     = "StringLike"
      values   = ["SSMmanaged"]
      variable = "ssm:resourceTag/Name"
    }
  }
  statement {
    effect    = "Allow"
    actions   = ["ssm:StartAutomationExecution"]
    resources = ["arn:aws:ssm:*:${var.account_id}:automation-definition/Automation-RunPatchBaseline:*"]
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${var.account_id}:role/AWS-SystemsManager-AutomationExecutionRole"]
    effect    = "Allow"
  }
}

resource "aws_iam_policy" "ev_ssm_automation_execution_policy" {
  name        = "EVSSMAutomationExecutionPolicy"
  path        = "/service-role/"
  description = "Restricted SSM access to execute actions from Shared Services account."
  policy      = data.aws_iam_policy_document.ev_ssm_automation_execution_policy.json
}

data "aws_iam_policy_document" "ev_ssm_automation_execution_role" {
  version = "2012-10-17"
  statement {
    effect = "Allow"
    principals {
      identifiers = ["arn:aws:iam::267821145838:root"]
      type        = "AWS"
    }
    actions = ["sts:AssumeRole"]
  }
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = ["ssm.amazonaws.com"]
      type        = "Service"
    }
    effect = "Allow"
  }
}

resource "aws_iam_role" "ev_ssm_automation_execution_role" {
  name               = "EVSSMAutomationExecutionRole"
  assume_role_policy = data.aws_iam_policy_document.ev_ssm_automation_execution_role.json
  path               = "/"
  tags = merge(var.tags, {
    "Name" = "EVSSMAutomationExecutionRole"
  })
}

resource "aws_iam_role_policy_attachment" "EVSSMAutomationExecutionPolicy_evssmautomationexecutionrole_policy_attachment" {
  role       = aws_iam_role.ev_ssm_automation_execution_role.name
  policy_arn = aws_iam_policy.ev_ssm_automation_execution_policy.arn
}
