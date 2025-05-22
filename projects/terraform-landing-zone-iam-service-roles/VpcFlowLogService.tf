data "aws_iam_policy_document" "ev_cloud_watch_log_group_write_access_policy" {
  version = "2012-10-17"
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams"
    ]
    effect    = "Allow"
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ev_cloud_watch_log_group_write_access_policy" {
  name        = "CloudWatchLogGroupWrite"
  path        = "/service-role/"
  description = "service access to create and write to CW log groups"
  policy      = data.aws_iam_policy_document.ev_cloud_watch_log_group_write_access_policy.json
}

data "aws_iam_policy_document" "ev_vpc_flow_log_service_role" {
  version = "2012-10-17"
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = ["vpc-flow-logs.amazonaws.com"]
      type        = "Service"
    }
    effect = "Allow"
  }
}

resource "aws_iam_role" "ev_vpc_flow_log_service_role" {
  name               = "VpcFlowLogService"
  assume_role_policy = data.aws_iam_policy_document.ev_vpc_flow_log_service_role.json
  path               = "/"
  tags = merge(var.tags, {
    "Name" = "VpcFlowLogService"
  })
  lifecycle {
    ignore_changes = [role_last_used]
  }
}

resource "aws_iam_role_policy_attachment" "CloudWatchLogGroupWrite_vpcflowlogservice_policy_attachment" {
  role       = aws_iam_role.ev_vpc_flow_log_service_role.name
  policy_arn = aws_iam_policy.ev_cloud_watch_log_group_write_access_policy.arn
}
