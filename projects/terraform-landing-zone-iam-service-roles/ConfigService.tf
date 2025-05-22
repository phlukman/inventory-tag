data "aws_iam_policy_document" "ev_config_remediation_policy" {
  version = "2012-10-17"
  statement {
    effect = "Allow"
    actions = [
      "ec2:StartInstances",
      "ec2:StopInstances",
      "ec2:RebootInstances",
      "ec2:TerminateInstances"
    ]
    resources = ["arn:aws:ec2:*:*:instance/*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = ["arn:aws:sns:us-east-1:${var.account_id}:config-remediation-log-notification"]
  }
  statement {
    effect = "Allow"
    actions = [
      "ssm:CancelCommand",
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
      "ssm:ListCommands",
      "ssm:SendCommand",
      "ssm:GetAutomationExecution",
      "ssm:GetParameters",
      "ssm:StartAutomationExecution"
    ]
    resources = ["*"]
  }
  statement {
    effect = "Allow"
    actions = [
      "ec2:DescribeInstanceAttribute",
      "ec2:DescribeInstanceStatus",
      "ec2:DescribeInstances"
    ]
    resources = ["*"]
  }
  statement {
    effect = "Allow"
    actions = [
      "rds:DescribeDBProxyTargetGroups",
      "rds:DescribeDBInstanceAutomatedBackups",
      "rds:DescribeGlobalClusters",
      "rds:DescribeEngineDefaultParameters",
      "rds:DescribeDBProxyTargets",
      "rds:DescribeSourceRegions",
      "rds:StopDBCluster",
      "rds:DescribeDBSnapshots",
      "rds:DescribeDBSecurityGroups",
      "rds:DescribeReservedDBInstances",
      "rds:DescribeValidDBInstanceModifications",
      "rds:DescribeOrderableDBInstanceOptions",
      "rds:DescribeCertificates",
      "rds:DescribeOptionGroups",
      "rds:DescribeDBEngineVersions",
      "rds:DescribeDBSubnetGroups",
      "rds:DescribeExportTasks",
      "rds:DescribePendingMaintenanceActions",
      "rds:DescribeDBParameterGroups",
      "rds:DescribeDBClusterBacktracks",
      "rds:DescribeReservedDBInstancesOfferings",
      "rds:DescribeDBInstances",
      "rds:DescribeEngineDefaultClusterParameters",
      "rds:DescribeDBProxies",
      "rds:DescribeDBParameters",
      "rds:DescribeEventCategories",
      "rds:DescribeEvents",
      "rds:DescribeDBClusterSnapshotAttributes",
      "rds:DescribeDBClusterParameters",
      "rds:DescribeEventSubscriptions",
      "rds:DescribeDBLogFiles",
      "rds:StopDBInstance",
      "rds:DescribeDBSnapshotAttributes",
      "rds:ListTagsForResource",
      "rds:DescribeOptionGroupOptions",
      "rds:DescribeDBClusterEndpoints",
      "rds:DescribeDBClusters",
      "rds:DescribeAccountAttributes",
      "rds:DescribeDBClusterParameterGroups"
    ]
    resources = ["*"]
  }
  statement {
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      "arn:aws:lambda:*:*:function:SSM*",
      "arn:aws:lambda:*:*:function:*:SSM*"
    ]
  }
  statement {
    effect = "Allow"
    actions = [
      "states:DescribeExecution",
      "states:StartExecution"
    ]
    resources = [
      "arn:aws:states:*:*:stateMachine:SSM*",
      "arn:aws:states:*:*:execution:SSM*"
    ]
  }
  statement {
    effect = "Allow"
    actions = [
      "tag:GetResources"
    ]
    resources = ["*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      values   = ["ssm.amazonaws.com"]
      variable = "iam:PassedToService"
    }
  }
}

resource "aws_iam_policy" "ev_config_remediation_policy" {
  name        = "EvConfigRemediationPolicy"
  path        = "/"
  description = "Allows AWS Config service to remediate resources automatically"
  policy      = data.aws_iam_policy_document.ev_config_remediation_policy.json
}

data "aws_iam_policy_document" "ev_config_service" {
  version = "2012-10-17"
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = [
        "config.amazonaws.com",
        "ssm.amazonaws.com"
      ]
      type = "Service"
    }
    effect = "Allow"
  }
}

resource "aws_iam_role" "ev_config_service" {
  name               = "ConfigService"
  assume_role_policy = data.aws_iam_policy_document.ev_config_service.json
  path               = "/"
  tags = merge(var.tags, {
    "Name" = "ConfigService"
  })
  lifecycle {
    ignore_changes = [role_last_used]
  }
}

resource "aws_iam_role_policy_attachment" "AWS_ConfigRole_configservice_policy_attachment" {
  role       = aws_iam_role.ev_config_service.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWS_ConfigRole"
}

resource "aws_iam_role_policy_attachment" "EvConfigRemediationPolicy_configservice_policy_attachment" {
  role       = aws_iam_role.ev_config_service.name
  policy_arn = aws_iam_policy.ev_config_remediation_policy.arn
}
