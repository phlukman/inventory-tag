data "aws_iam_policy_document" "ev_ami_inventory" {
  version = "2012-10-17"
  statement {
    actions = ["ec2:DescribeImages", "ec2:DescribeInstances"]
    effect    = "Allow"
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ev_ami_inventory" {
  name        = "EvMSCIDBAMIInventoryPolicy"
  path        = "/"
  description = "Permissions required to get inventory of all AMIs and their metadata"
  policy      = data.aws_iam_policy_document.ev_ami_inventory.json
}

resource "aws_iam_role" "ev_ami_inventory" {
  name               = "EvMSCIDBAMIInventoryMemberAccountRole"
  path               = "/"
  assume_role_policy = jsonencode({
      Version = "2012-10-17",
      Statement = [{
          Effect = "Allow",
          Principal = {
              AWS = local.cidb_lambda_exec_role_arns
          },
          Action = "sts:AssumeRole"
      }]
  })
  tags = merge(var.tags, {
    Name = "EvMSCIDBAMIInventoryMemberAccountRole"
  })
}

resource "aws_iam_role_policy_attachment" "ev_ami_inventory" {
  role       = aws_iam_role.ev_ami_inventory.name
  policy_arn = aws_iam_policy.ev_ami_inventory.arn
}