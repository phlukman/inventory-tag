###############################################
# main.tf - Cross-Account Access Roles Module
###############################################

provider "aws" {
  region = "us-east-1"
  alias  = "target_0"
  # Either direct credentials or assume role
  assume_role {
    role_arn = "arn:aws:iam::053210025230:role/TO_BE_CREATED"
  }
}

# Provider for the source account
# provider "aws" {
#   alias  = "source"
#   region = var.region
#   # Credentials handled via environment variables or shared credentials file
# }

# Provider configuration for each target account
# locals {
#   target_providers = {
#     for idx, account in var.target_accounts :
#     account.account_id => {
#       account_id = account.account_id
#       name       = account.name
#       provider   = "aws.target_${idx}"
#     }
#   }
# }


###############################################
# IAM Role in Source Account
###############################################

# Source account role that will be used to assume roles in target accounts
resource "aws_iam_role" "source_role_local_dev" {
 
  name     = var.source_role_name
  
  # This assume role policy should allow whatever service/entity will be using this role
  # For Lambda, it would be lambda.amazonaws.com
  # For EC2, it would be ec2.amazonaws.com
  # For direct use by an IAM user, it would be a Principal with the user's ARN
 
   # Trust policy allowing it to be assumed by the federated user
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::477591219415:role/Engineer"
        },
        # # Optional: Add a condition to limit to specific sessions
        # Condition = {
        #   StringEquals = {
        #     "aws:PrincipalTag/email": "PLukman@eatonvance.com"
        #   }
        # }
      }
    ]
  })
  
  # tags = var.tags
}

# Policy allowing source role to assume roles in target accounts
resource "aws_iam_policy" "assume_role_policy" {
  name        = "${var.source_role_name}-assume-policy"
  description = "Allows assuming roles in target accounts"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Resource = [ "arn:aws:iam::053210025230:role/cidb-inventory-role" ]
         # [for account in var.target_accounts :
         # "arn:aws:iam::${account.account_id}:role/${var.target_role_name}"
         # ]
      }
    ]
  })
  
  # tags = var.tags
}

# # Attach assume role policy to source role
resource "aws_iam_role_policy_attachment" "source_assume_role_attachment" {
  role       = aws_iam_role.source_role_local_dev.name
  policy_arn = aws_iam_policy.assume_role_policy.arn
}

# ###############################################
# # IAM Roles in Target Accounts
# ###############################################

# # This resource policy defines what the target role should be allowed to do
# # This is created in each target account and attached to the respective roles
# resource "aws_iam_policy" "target_resource_policy" {
#   for_each = {
#     for account in var.target_accounts : account.account_id => account
#     if lookup(account, "provider", "") != ""
#   }
  
#   provider    = aws[each.value.provider]
#   name        = "${var.target_role_name}-permissions"
#   description = "Permissions for the resource reader role in target account"
  
#   policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [
#       {
#         Effect = "Allow"
#         Action = [
#           # AppConfig
#           "appconfig:ListDeploymentStrategies",
#           "appconfig:GetDeploymentStrategy",
#           "appconfig:ListTagsForResource",
          
#           # AutoScaling
#           "autoscaling:DescribePolicies",
#           "autoscaling:DescribeScalingActivities",
#           "autoscaling:DescribeTags",
          
#           # Cassandra (Keyspaces)
#           "cassandra:Select",
#           "cassandra:ListTables",
#           "cassandra:ListKeyspaces",
#           "cassandra:GetTags",
          
#           # CloudWatch
#           "cloudwatch:DescribeAlarms",
#           "cloudwatch:DescribeAlarmHistory",
#           "cloudwatch:ListTagsForResource",
          
#           # CodeDeploy
#           "codedeploy:ListDeploymentConfigs",
#           "codedeploy:GetDeploymentConfig",
#           "codedeploy:ListTagsForResource",
          
#           # EC2
#           "ec2:DescribeFleets",
#           "ec2:DescribeSpotFleetRequests",
#           "ec2:DescribeTags",
          
#           # Events (EventBridge)
#           "events:ListRules",
#           "events:DescribeRule",
#           "events:ListTagsForResource",
          
#           # IAM
#           "iam:ListPolicies",
#           "iam:GetPolicy",
#           "iam:GetPolicyVersion",
#           "iam:ListEntitiesForPolicy",
#           "iam:ListPolicyTags",
          
#           # KMS
#           "kms:ListAliases",
#           "kms:ListResourceTags",
#           "kms:DescribeKey",
          
#           # Route53
#           "route53:ListHostedZones",
#           "route53:GetHostedZone",
#           "route53:ListTagsForResource"
#         ]
#         Resource = "*"
#       }
#     ]
#   })
  
#   tags = var.tags
# }

# # Create the roles in each target account
# resource "aws_iam_role" "target_role" {
#   for_each = {
#     for account in var.target_accounts : account.account_id => account
#     if lookup(account, "provider", "") != ""
#   }
  
#   provider = aws[each.value.provider]
#   name     = var.target_role_name
  
#   # Trust policy allowing the source account role to assume this role
#   assume_role_policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [
#       {
#         Effect = "Allow"
#         Principal = {
#           AWS = "arn:aws:iam::${var.source_account_id}:role/${var.source_role_name}"
#         }
#         Action = "sts:AssumeRole"
#       }
#     ]
#   })
  
#   tags = var.tags
# }

# # Attach the permissions policy to each target role
# resource "aws_iam_role_policy_attachment" "target_policy_attachment" {
#   for_each = {
#     for account in var.target_accounts : account.account_id => account
#     if lookup(account, "provider", "") != ""
#   }
  
#   provider   = aws[each.value.provider]
#   role       = aws_iam_role.target_role[each.key].name
#   policy_arn = aws_iam_policy.target_resource_policy[each.key].arn
# }

# ###############################################
# # Policy documents for manual role creation
# ###############################################

# # These locals provide the policy documents that can be used to manually create roles
# # in target accounts that don't have providers configured
# locals {
#   target_role_policy_document = jsonencode({
#     Version = "2012-10-17"
#     Statement = [
#       {
#         Effect = "Allow"
#         Action = [
#           # AppConfig
#           "appconfig:ListDeploymentStrategies",
#           "appconfig:GetDeploymentStrategy",
#           "appconfig:ListTagsForResource",
          
#           # AutoScaling
#           "autoscaling:DescribePolicies",
#           "autoscaling:DescribeScalingActivities",
#           "autoscaling:DescribeTags",
          
#           # Cassandra (Keyspaces)
#           "cassandra:Select",
#           "cassandra:ListTables",
#           "cassandra:ListKeyspaces",
#           "cassandra:GetTags",
          
#           # CloudWatch
#           "cloudwatch:DescribeAlarms",
#           "cloudwatch:DescribeAlarmHistory",
#           "cloudwatch:ListTagsForResource",
          
#           # CodeDeploy
#           "codedeploy:ListDeploymentConfigs",
#           "codedeploy:GetDeploymentConfig",
#           "codedeploy:ListTagsForResource",
          
#           # EC2
#           "ec2:DescribeFleets",
#           "ec2:DescribeSpotFleetRequests",
#           "ec2:DescribeTags",
          
#           # Events (EventBridge)
#           "events:ListRules",
#           "events:DescribeRule",
#           "events:ListTagsForResource",
          
#           # IAM
#           "iam:ListPolicies",
#           "iam:GetPolicy",
#           "iam:GetPolicyVersion",
#           "iam:ListEntitiesForPolicy",
#           "iam:ListPolicyTags",
          
#           # KMS
#           "kms:ListAliases",
#           "kms:ListResourceTags",
#           "kms:DescribeKey",
          
#           # Route53
#           "route53:ListHostedZones",
#           "route53:GetHostedZone",
#           "route53:ListTagsForResource"
#         ]
#         Resource = "*"
#       }
#     ]
#   })
  
#   # Trust policy for target roles (to be created in target accounts)
#   target_role_trust_policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [
#       {
#         Effect = "Allow"
#         Principal = {
#           AWS = "arn:aws:iam::${var.source_account_id}:role/${var.source_role_name}"
#         }
#         Action = "sts:AssumeRole"
#       }
#     ]
#   })
# }

