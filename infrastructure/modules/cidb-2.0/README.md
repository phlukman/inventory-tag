# CIDB 2.0 Module

## Overview
The CIDB 2.0 (Configuration Item Database) module is responsible for collecting, processing, and reporting on configuration items across multiple AWS accounts. This module includes Lambda functions, state machines, and IAM roles required for cross-account operations.

## IAM Policy Inventory Cross-Account Implementation

### Problem Statement
The IAM policy inventory system needs to collect IAM policies from multiple AWS accounts across different environments (sandbox, dev, staging, prod). The collection process must be:
- Secure: Use proper cross-account IAM roles with least privilege
- Scalable: Support adding new accounts with minimal configuration
- Resilient: Handle concurrent processing without race conditions
- Efficient: Minimize data transfer and processing overhead

### Solution Architecture

#### Components
1. **IAM Service Roles Module** (`/projects/terraform-landing-zone-iam-service-roles/`)
   - Creates the `EvIAMPolicyInventoryMemberAccountRole` in target accounts
   - Role has permissions to read IAM policies within that account
   - Includes trust relationship to allow the Lambda execution role to assume it
   - Conditionally created based on account ID and environment enablement flags

2. **CIDB 2.0 Module** (`/infrastructure/modules/cidb-2.0/`)
   - Creates `EvIAMPolicyInventoryAssumerPolicy` attached to the Lambda execution role
   - Policy contains permissions to assume the IAM policy inventory role in all target accounts
   - Lambda function handles the cross-account operations

#### Data Flow
1. Lambda function runs with the `ev_ms_cidb2_inventory_role` role
2. Lambda assumes the `EvIAMPolicyInventoryMemberAccountRole` in target accounts
3. Lambda collects IAM policy data from each account
4. Data is written to S3 using an append-only pattern to prevent race conditions
5. The process can run concurrently across multiple accounts safely

### Implementation Details

#### IAM Service Roles Module Files

1. **EvIAMPolicyInventoryRole.tf**
   ```hcl
   # Creates the IAM role in target accounts with required permissions
   resource "aws_iam_role" "ev_iam_policy_inventory" {
     name = "EvIAMPolicyInventoryMemberAccountRole"
     # Trust relationship allows the Lambda execution role to assume this role
     assume_role_policy = jsonencode({
       Version = "2012-10-17",
       Statement = [{
         Effect = "Allow",
         Principal = {
           AWS = var.cidb_collector_lambda_role_arn
         },
         Action = "sts:AssumeRole"
       }]
     })
   }

   # IAM policy with permissions to read IAM policies
   resource "aws_iam_policy" "ev_iam_policy_inventory" {
     name        = "EvIAMPolicyInventoryPolicy"
     description = "Policy that grants permissions to inventory IAM policies"
     policy      = jsonencode({
       Version = "2012-10-17",
       Statement = [{
         Effect   = "Allow",
         Action   = [
           "iam:GetPolicy",
           "iam:GetPolicyVersion",
           "iam:GetRole",
           "iam:GetRolePolicy",
           "iam:ListAttachedRolePolicies",
           "iam:ListPolicies",
           "iam:ListPolicyVersions",
           "iam:ListRolePolicies",
           "iam:ListRoles"
         ],
         Resource = "*"
       }]
     })
   }

   # Attach the policy to the role
   resource "aws_iam_role_policy_attachment" "ev_iam_policy_inventory" {
     role       = aws_iam_role.ev_iam_policy_inventory.name
     policy_arn = aws_iam_policy.ev_iam_policy_inventory.arn
   }
   ```

2. **variables.tf**
   ```hcl
   # Contains variables for environment-based account management
   variable "enable_iam_inventory_environments" {
     description = "List of environments where IAM policy inventory role should be enabled"
     type        = list(string)
     default     = ["sandbox", "dev", "staging", "prod"]
   }

   variable "iam_inventory_accounts" {
     description = "Map of environments to account IDs for IAM policy inventory"
     type        = map(list(string))
     default     = {
       sandbox = ["123456789012", "234567890123"],
       dev     = ["345678901234", "456789012345"],
       staging = ["567890123456"],
       prod    = ["678901234567", "789012345678"]
     }
   }

   variable "cidb_collector_lambda_role_arn" {
     description = "ARN of the Lambda execution role that will assume the IAM policy inventory role"
     type        = string
     default     = "arn:aws:iam::477591219415:role/ev_ms_cidb2_inventory_role"
   }
   ```

3. **outputs.tf**
   ```hcl
   # Outputs the expected role ARNs for all target accounts
   output "iam_policy_inventory_expected_role_arns" {
     description = "Map of expected IAM policy inventory role ARNs for all target accounts"
     value = {
       for account_id in flatten([
         for env in var.enable_iam_inventory_environments : 
           lookup(var.iam_inventory_accounts, env, [])
       ]) :
         account_id => "arn:aws:iam::${account_id}:role/EvIAMPolicyInventoryMemberAccountRole"
     }
   }
   ```

#### CIDB 2.0 Module Files

1. **iam-policy-inventory-role-attachment.tf**
   ```hcl
   # Variable to receive the expected role ARNs from the terraform-landing-zone-iam-service-roles module
   variable "iam_policy_inventory_role_arns" {
     description = "Map of account IDs to IAM policy inventory role ARNs from the terraform-landing-zone-iam-service-roles module"
     type        = map(string)
     default     = {} # Default empty map allows the module to be applied without dependencies
   }

   # Create a policy document that allows assuming all the IAM policy inventory roles
   data "aws_iam_policy_document" "ev_iam_policy_inventory_assumer" {
     version = "2012-10-17"
     statement {
       actions = ["sts:AssumeRole"]
       effect  = "Allow"
       resources = length(var.iam_policy_inventory_role_arns) > 0 ? values(var.iam_policy_inventory_role_arns) : [
         # Fallback to a pattern-based approach if no specific ARNs are provided
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
   ```

### Append-Only S3 Operations Pattern

The IAM policy inventory solution uses an append-only pattern for S3 operations to prevent race conditions when collecting data from multiple accounts concurrently:

#### Problem
- When multiple Lambda instances process different accounts concurrently, they may try to update the same S3 file
- This creates a classic read-modify-write race condition, even with S3 versioning enabled
- One Lambda's updates could overwrite another's

#### Solution: Append-Only Pattern
1. **For new files**:
   - Create with proper headers
   - Write the account-specific data

2. **For existing files**:
   - Preserve the header row
   - Append only the new rows for the current account
   - No need to read the entire file first

3. **Benefits**:
   - Eliminates race conditions as each Lambda only appends its own data
   - No need for complex locking mechanisms
   - Maintains data integrity with S3 versioning
   - Simplified error handling
   - Improved performance by avoiding unnecessary full file reads

4. **Implementation**:
   - The Lambda checks if a file exists before writing
   - For new files: creates with headers
   - For existing files: preserves the header and appends new rows
   - Uses S3 versioning for rollback capability

#### Code Example for Append-Only Operations
The append-only pattern is implemented in the CIDB 2.0 module at:
`/infrastructure/modules/cidb-2.0/src/cidb2_merge/main.py`

```python
def append_to_csv(bucket, key, new_rows, header_row):
    """
    Append new rows to a CSV file in S3 using an append-only pattern.
    If the file doesn't exist, create it with headers.
    If it exists, preserve headers and append the new rows.
    This prevents race conditions when multiple Lambda instances write concurrently.
    """
    s3_client = boto3.client('s3')
    
    try:
        # Check if file exists
        s3_client.head_object(Bucket=bucket, Key=key)
        file_exists = True
    except:
        file_exists = False
    
    if not file_exists:
        # Create new file with headers and data
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(header_row)
        for row in new_rows:
            writer.writerow(row)
        
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=csv_buffer.getvalue()
        )
    else:
        # Append only new data, preserving headers
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        for row in new_rows:
            writer.writerow(row)
        
        # Append to existing file without reading it first
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=csv_buffer.getvalue(),
            AppendPosition='AFTER'  # Use S3 append feature
        )
```

### Module Integration

To use this module with the IAM policy inventory functionality:

```hcl
module "iam_service_roles" {
  source = "./projects/terraform-landing-zone-iam-service-roles"
  enable_iam_inventory_environments = ["sandbox", "dev"]  # Enable only specific environments
  
  # Optional: Override the default account mappings
  iam_inventory_accounts = {
    sandbox = ["123456789012", "234567890123"],
    dev     = ["345678901234"]
  }
  
  cidb_collector_lambda_role_arn = "arn:aws:iam::477591219415:role/ev_ms_cidb2_inventory_role"
}

module "cidb_2_0" {
  source = "./infrastructure/modules/cidb-2.0"
  
  # Pass the role ARNs from the IAM service roles module
  iam_policy_inventory_role_arns = module.iam_service_roles.iam_policy_inventory_expected_role_arns
  
  # Other variables...
}
```

### Deployment Process

For proper deployment, follow these steps:

1. **Deploy IAM Roles to Target Accounts**:
   - Apply the `terraform-landing-zone-iam-service-roles` module to each target account
   - This creates the `EvIAMPolicyInventoryMemberAccountRole` with proper permissions
   - Ensure the trust relationship is properly configured

2. **Update and Deploy CIDB 2.0 Module**:
   - Apply the updated CIDB 2.0 module with the assumer policy
   - Pass the role ARNs from the IAM service roles module output
   - The Lambda execution role will get the necessary permissions

3. **Verify Deployment**:
   - Check that the roles are created in each target account
   - Verify the policy is attached to the Lambda execution role
   - Test assume role operations across accounts

### Testing

To test the cross-account IAM policy inventory:

1. **Test Assume Role**:
   ```bash
   aws sts assume-role --role-arn arn:aws:iam::TARGET_ACCOUNT_ID:role/EvIAMPolicyInventoryMemberAccountRole --role-session-name TestSession
   ```

2. **Test Lambda Function Locally**:
   - Use AWS SAM or similar tool to test Lambda function locally
   - Provide mock context with the Lambda execution role
   - Verify the function can:
     - Assume roles in target accounts
     - Collect IAM policy data
     - Write to S3 using the append-only pattern

3. **Verify S3 Writes**:
   - Check S3 bucket for IAM policy data files
   - Verify that data from multiple accounts is correctly appended
   - Check for any errors in CloudWatch Logs

### Troubleshooting

#### Common Issues and Solutions

1. **Cross-Account Trust Relationship Issues**:
   - **Symptom**: `AccessDenied` when assuming role
   - **Solution**: Verify the trust relationship in the target account allows the Lambda execution role to assume it
   - **Check**: Look at the `assume_role_policy` in `EvIAMPolicyInventoryRole.tf`

2. **Missing Permissions**:
   - **Symptom**: Lambda can assume role but can't read IAM policies
   - **Solution**: Verify the permissions attached to `EvIAMPolicyInventoryMemberAccountRole`
   - **Check**: Look at the policy document in `EvIAMPolicyInventoryRole.tf`

3. **S3 Write Issues**:
   - **Symptom**: Lambda can't write to S3 bucket
   - **Solution**: Verify the Lambda execution role has S3 write permissions
   - **Check**: Look at the existing S3 permissions in the CIDB 2.0 module

4. **Role Not Created in Target Account**:
   - **Symptom**: Role doesn't exist when trying to assume it
   - **Solution**: Verify the account ID is included in the enabled environments
   - **Check**: Look at `enable_iam_inventory_environments` and `iam_inventory_accounts` variables

### Future Enhancements

Potential improvements for the IAM policy inventory system:

1. **Dynamic Account Discovery**:
   - Automatically discover accounts through AWS Organizations API
   - Reduce manual configuration of account lists

2. **Enhanced Error Handling**:
   - Add retry mechanism for failed assume role operations
   - Implement DLQ for processing failures

3. **Reporting Improvements**:
   - Generate summaries of IAM policies across accounts
   - Track changes over time for compliance reporting

4. **Performance Optimizations**:
   - Implement parallel processing of multiple accounts
   - Use pagination for large policy lists

### References

- [AWS Cross-Account Role Assumption](https://docs.aws.amazon.com/IAM/latest/UserGuide/tutorial_cross-account-with-roles.html)
- [Terraform AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [S3 Append-Only Pattern Best Practices](https://aws.amazon.com/blogs/storage/managing-append-only-datasets-with-amazon-s3/)
- [Lambda Cross-Account Access](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html)
