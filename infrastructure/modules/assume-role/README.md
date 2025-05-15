# AWS Cross-Account Access Roles Module

This Terraform module creates IAM roles in both source and target AWS accounts to enable cross-account access for reading AWS resources. The module follows AWS best practices for cross-account access using STS AssumeRole.

## Features

- Creates a source account role with permission to assume roles in specified target accounts
- Creates roles in target accounts that trust the source account role
- Provides policy documents for manual role creation in target accounts without providers
- Configures access to the specified AWS resource types across accounts

## Prerequisites

- Terraform 1.0 or newer
- AWS provider 4.0 or newer
- AWS CLI configured with appropriate credentials
- Permissions to create IAM roles in source and target accounts

## Resource Types Supported

The module is configured to permit reading the following AWS resource types:

1. AWS::AppConfig::DeploymentStrategy
2. AWS::AutoScaling::ScalingPolicy
3. AWS::Cassandra::Keyspace
4. AWS::CloudWatch::Alarm
5. AWS::CodeDeploy::DeploymentConfig
6. AWS::EC2::EC2Fleet
7. AWS::Events::Rule
8. AWS::IAM::Policy
9. AWS::KMS::Alias
10. AWS::Route53::HostedZone

## Usage

### Basic Usage

```hcl
module "cross_account_roles" {
  source = "path/to/module"
  
  providers = {
    aws.source = aws.source
  }
  
  source_account_id = "123456789012"  # The account where the source role will be created
  
  target_accounts = [
    {
      account_id = "111111111111"
      name       = "Production"
      provider   = "aws.target_0"  # Provider alias for this account
    },
    {
      account_id = "222222222222"
      name       = "Development"
      provider   = "aws.target_1"  # Provider alias for this account
    },
    {
      account_id = "333333333333"
      name       = "Testing"
      provider   = ""  # Empty provider means no automatic role creation
    }
  ]
  
  # Optional parameters
  source_role_name = "ResourceReaderRole"  # Default: ResourceReaderSourceRole
  target_role_name = "ResourceReaderRole"  # Default: ResourceReaderRole
  region           = "us-east-1"           # Default: us-east-1
  
  tags = {
    Environment = "production"
    Owner       = "platform-team"
  }
}
```

### Provider Configuration

You must configure providers for each account:

```hcl
# Source account provider
provider "aws" {
  region = "us-east-1"
  alias  = "source"
  # Authentication via environment variables, shared credentials, etc.
}

# Target account providers
provider "aws" {
  region = "us-east-1"
  alias  = "target_0"
  # Either direct credentials or assume role
  assume_role {
    role_arn = "arn:aws:iam::111111111111:role/OrganizationAccountAccessRole"
  }
}

provider "aws" {
  region = "us-east-1"
  alias  = "target_1"
  assume_role {
    role_arn = "arn:aws:iam::222222222222:role/OrganizationAccountAccessRole"
  }
}
```

## Implementation Process

### 1. Configure AWS Providers

For each target account where you want to automatically create roles, you need a provider configuration.

### 2. Deploy the Module

```bash
# Initialize Terraform
terraform init

# Plan the deployment
terraform plan

# Apply the changes
terraform apply
```

### 3. Manual Role Creation in Target Accounts

For target accounts without provider configurations, you need to manually create IAM roles:

a. Get the role policy and trust policy from Terraform outputs:
```bash
terraform output target_role_policy_document > target_role_policy.json
terraform output target_role_trust_policy > target_role_trust_policy.json
```

b. Create the role in each target account using AWS CLI:
```bash
# Create the role
aws iam create-role \
    --role-name ResourceReaderRole \
    --assume-role-policy-document file://target_role_trust_policy.json \
    --profile target-account

# Create the policy
aws iam create-policy \
    --policy-name ResourceReaderPolicy \
    --policy-document file://target_role_policy.json \
    --profile target-account

# Attach the policy to the role
aws iam attach-role-policy \
    --role-name ResourceReaderRole \
    --policy-arn arn:aws:iam::TARGET_ACCOUNT_ID:policy/ResourceReaderPolicy \
    --profile target-account
```

The example usage includes a local_file resource that generates a shell script for this purpose.

## Module Structure

- `main.tf` - Main Terraform configuration file
- `outputs.tf` - Module outputs

## Variables

| Name | Description | Type | Default |
|------|-------------|------|---------|
| `source_account_id` | Source AWS account ID where the source role will be created | `string` | Required |
| `target_accounts` | List of target AWS accounts to create roles in | `list(object)` | Required |
| `source_role_name` | Name of the role in the source account | `string` | `"ResourceReaderSourceRole"` |
| `target_role_name` | Name of the role to be created in target accounts | `string` | `"ResourceReaderRole"` |
| `region` | AWS region for deployment | `string` | `"us-east-1"` |
| `tags` | Tags to apply to resources | `map(string)` | `{}` |

The `target_accounts` variable is a list of objects with the following structure:
```hcl
{
  account_id = string  # AWS account ID
  name       = string  # Human-readable name
  provider   = string  # Provider alias (empty string for no automatic role creation)
}
```

## Outputs

| Name | Description |
|------|-------------|
| `source_role_arn` | ARN of the source account role |
| `target_role_arns` | Map of account IDs to ARNs of the target account roles |
| `target_role_policy_document` | Policy document for the target role |
| `target_role_trust_policy` | Trust policy for the target role |

## Security Considerations

- The module follows the principle of least privilege
- Only necessary permissions are granted to the target roles
- Cross-account access is restricted to read-only operations
- The source role will use temporary credentials via STS AssumeRole when assuming target roles

## Troubleshooting

1. **Role Creation Failures**:
   - Ensure you have sufficient permissions in each account
   - Check that provider configurations are correct

2. **Role Assumption Failures**:
   - Ensure trust relationships are properly configured
   - Verify that the source role has sts:AssumeRole permission
   - Check for typos in account IDs and role names

3. **Permission Issues**:
   - Review the IAM policies attached to the roles
   - Verify that the roles have the necessary permissions

## Integrating with Lambda or Other Services

To use these roles with Lambda or other AWS services, you'll need to configure your Lambda function to assume the source role, which in turn can assume roles in the target accounts.

Your Lambda function code should use the boto3 STS client to assume roles in target accounts:

```python
import boto3

def assume_role(account_id, role_name):
    """Assume a role in another AWS account"""
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    
    sts_client = boto3.client('sts')
    response = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=f"AssumedRoleSession-{account_id}"
    )
    
    credentials = response['Credentials']
    
    # Create a new session with the assumed role credentials
    assumed_session = boto3.Session(
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )
    
    return assumed_session
```

## License

This module is provided under the MIT License.