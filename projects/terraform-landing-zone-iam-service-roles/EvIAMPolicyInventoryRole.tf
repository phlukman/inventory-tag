data "aws_iam_policy_document" "ev_iam_policy_inventory" {
  version = "2012-10-17"
  statement {
    actions = [
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicies",
      "iam:ListPolicyVersions",
      "iam:ListEntitiesForPolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListAttachedUserPolicies",
      "iam:ListAttachedGroupPolicies",
      "iam:ListRoles",
      "iam:ListUsers",
      "iam:ListGroups"
    ]
    effect    = "Allow"
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ev_iam_policy_inventory" {
  name        = "EvIAMPolicyInventoryPolicy"
  path        = "/"
  description = "Permissions required to inventory IAM policies across accounts"
  policy      = data.aws_iam_policy_document.ev_iam_policy_inventory.json
}

# Get the current AWS account ID
data "aws_caller_identity" "current" {}

# Define locals for account management and tracking enabled environments
locals {
  # Get all enabled accounts based on the environments enabled
  enabled_accounts = flatten([
    for env in var.enable_iam_inventory_environments : 
      lookup(var.iam_inventory_accounts, env, [])
  ])
  
  # Determine if the current account should have the IAM inventory role
  # This allows the Terraform to check if the current account is in the target list
  current_account_needs_role = contains(local.enabled_accounts, data.aws_caller_identity.current.account_id)
}

resource "aws_iam_role" "ev_iam_policy_inventory" {
  # Only create the role if the current account is in the enabled accounts list
  count              = local.current_account_needs_role ? 1 : 0
  name               = "EvIAMPolicyInventoryMemberAccountRole"
  path               = "/"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        # Use the Lambda execution role ARN from the variable
        AWS = var.cidb_collector_lambda_role_arn
      },
      Action = "sts:AssumeRole"
    }]
  })
  tags = merge(var.tags, {
    Name = "EvIAMPolicyInventoryMemberAccountRole"
  })
}

resource "aws_iam_role_policy_attachment" "ev_iam_policy_inventory" {
  # Only create the attachment if the role exists
  count      = local.current_account_needs_role ? 1 : 0
  role       = aws_iam_role.ev_iam_policy_inventory[0].name
  policy_arn = aws_iam_policy.ev_iam_policy_inventory.arn
}
