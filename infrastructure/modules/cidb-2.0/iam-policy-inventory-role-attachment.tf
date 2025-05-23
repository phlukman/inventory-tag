# This file creates a policy for the CIDB Lambda to assume IAM policy inventory roles across accounts
# and attaches it to the Lambda execution role



# Create a policy document that allows assuming all the IAM policy inventory roles
data "aws_iam_policy_document" "ev_iam_policy_inventory_assumer" {
  version = "2012-10-17"
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    resources = length(var.iam_policy_inventory_role_arns) > 0 ? values(var.iam_policy_inventory_role_arns) : [
      # Fallback to a pattern-based approach if no specific ARNs are provided
      # This ensures the module can be applied before the IAM roles are created
      "arn:aws:iam::*:role/EvIAMPolicyInventoryMemberAccountRole"
    ]
  }
}

# Create the policy
resource "aws_iam_policy" "ev_iam_policy_inventory_assumer" {
  name        = "EvIAMPolicyInventoryAssumerPolicy"
  path        = "/"
  description = "Policy that allows assuming IAM policy inventory roles across target accounts"
  policy      = data.aws_iam_policy_document.ev_iam_policy_inventory_assumer.json
}

# Attach the policy to the Lambda execution role
resource "aws_iam_role_policy_attachment" "lambda_iam_policy_inventory_assumer" {
  role       = aws_iam_role.ev_ms_cidb2_inventory_role.name
  policy_arn = aws_iam_policy.ev_iam_policy_inventory_assumer.arn
}



# Implementation Notes:
# 1. This policy allows the Lambda to assume the EvIAMPolicyInventoryMemberAccountRole
#    in all target accounts.
# 2. The Lambda will use this to collect IAM policy data from multiple accounts concurrently.
# 3. When writing data to S3, the Lambda uses an append-only pattern to prevent race conditions:
#    - Each Lambda execution appends only its own data without full file reads
#    - No need for complex locking mechanisms
#    - Maintains data integrity with S3 versioning
#    - Improves performance by avoiding unnecessary reads
# 4. To integrate with main Terraform configuration:
#    module "cidb_2_0" {
#      source = "./infrastructure/modules/cidb-2.0"
#      iam_policy_inventory_role_arns = module.iam_service_roles.iam_policy_inventory_expected_role_arns
#    }
