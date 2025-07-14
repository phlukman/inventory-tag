# AWS Organization Accounts Lister

This module implements a Lambda function that lists all AWS accounts in an organization and collects detailed information by assuming a role in each account. The function can exclude specific accounts from processing and runs on a scheduled basis.

## Features

- Lists all active accounts in an AWS Organization
- Assumes a role in each account to collect additional information:
  - Account aliases
  - OU structure and paths
  - Tags applied to accounts
- Supports excluding specific accounts from processing through:
  - Environment variables
- Categorizes accounts by OU structure and naming patterns
- Stores results in S3 bucket for further processing
- Runs on a scheduled basis (daily at 6 AM UTC by default)
- Uses role assumption for secure cross-account access

## Prerequisites

- AWS Organization set up
- The role specified by `ROLE_TO_ASSUME` (default: `EvResourceTagInventoryMemberAccountRole`) must exist in member accounts
- Lambda execution role must have permission to call Organizations API and assume role in member accounts
- S3 bucket for storing output files

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BUCKET_NAME` | S3 bucket to store account information | N/A (Required) |
| `ROLE_TO_ASSUME` | Role name to assume in member accounts | `EvResourceTagInventoryMemberAccountRole` |
| `MANAGEMENT_ACCOUNT_ID` | AWS Organization management account ID | N/A (Required) |
| `MANAGEMENT_ROLE_NAME` | Role name to assume in management account | `EVCIDB-Crossaccount-Role` |
| `ENV_EXCLUDED_ACCOUNTS` | JSON-encoded array of account IDs to exclude | `[]` (Empty array) |
| `PRINT_DETAILS` | Whether to print detailed account information | `false` |

## Output

### S3 Output

The Lambda function outputs a CSV file to S3 with account information, including account IDs, aliases, OU paths, and tags. The file is stored in the following path format:

```
s3://${BUCKET_NAME}/Custom/org-account-lister/org-account-lister-${year}-${month}-${day}.csv
```

For example: `s3://my-bucket/Custom/org-account-lister/org-account-lister-2025-june-15.csv`

The CSV contains the following columns:
- AccountId
- AccountAlias
- OUPath
- Tags (JSON format)


The excluded accounts will not appear in any of these lists.

### Lambda Response

The Lambda function returns a JSON response with the following structure:

```json
{
  "statusCode": 200,
  "body": {
    "message": "Successfully processed 62 AWS organization accounts",
    "total_accounts": 62,
    "accounts_with_tags": 54,
    "accounts_with_ou_path": 62,
    "output_formats": ["json", "csv"],
    "output_path": "Custom/org-account-lister/org-account-lister-2025-june-15.csv"
  }
}
```

## Account Exclusion

The function supports excluding specific AWS accounts from processing through two methods:

1. **Environment Variables**: Setting the `ENV_EXCLUDED_ACCOUNTS` environment variable with a JSON-encoded array of account IDs.
   ```
   ENV_EXCLUDED_ACCOUNTS = ["123456789012", "234567890123"]
   ```

## Scheduling

The Lambda function is scheduled to run daily at 6 AM UTC using EventBridge Scheduler. This ensures that up-to-date account information is always available for downstream processing. The schedule is defined as a cron expression:

```
cron(0 2 * * ? *)  # Daily at 6 AM UTC
```

## Implementation Details

### Excluded Accounts Flow

The account exclusion functionality works as follows:

1. At initialization, the Lambda retrieves the `ENV_EXCLUDED_ACCOUNTS` environment variable:
   ```python
   ENV_EXCLUDED_ACCOUNTS = json.loads(os.environ.get('ENV_EXCLUDED_ACCOUNTS', "[]"))
   ```

2. The `list_accounts` method accepts an optional `excluded_accounts` parameter:
   ```python
   def list_accounts(self, excluded_accounts=None):
       # Initialize excluded_accounts to empty list if None
       if excluded_accounts is None:
           excluded_accounts = []
           
       # Filter out excluded accounts when listing
       if account['Status'] == 'ACTIVE' and account['Id'] not in excluded_accounts:
           accounts.append({...})
   ```

3. The `list_account_details` method passes the exclusion list to `list_accounts`:
   ```python
   def list_account_details(self, excluded_accounts=None):
       accounts = self.list_accounts(excluded_accounts)
       # Process accounts...
   ```

4. The `lambda_handler` uses the environment variable for exclusions:
   ```python
   # Get detailed account information including tags and OU paths
   accounts = lister.list_account_details(ENV_EXCLUDED_ACCOUNTS)
   ```

The Terraform configuration provides the excluded accounts as a JSON-encoded environment variable:

```terraform
environment_variables = {
  ENV_EXCLUDED_ACCOUNTS = jsonencode(local.env_excluded_accounts)
}
```

Where `local.env_excluded_accounts` is defined in `locals.tf` as an array of account IDs.

## Terraform Integration

The function is deployed using Terraform with the following resources:

- **Lambda function**: `org_accounts_lister_lambda` module
  - Python 3.10 runtime
  - 15-minute timeout
  - 512MB memory allocation

- **EventBridge Scheduler**: `aws_scheduler_schedule` resource
  - Daily schedule at 2 AM UTC
  - Flexible time window disabled

- **IAM Components**:
  - Scheduler execution role
  - Lambda invoke policy
  - Role policy attachments
  - Lambda permission for EventBridge invocation

- **Environment Variables**:
  - S3 bucket for output
  - Role names for cross-account access
  - Excluded accounts (JSON-encoded array)

See the `org_accounts_lister.tf` and `org_accounts_policy.tf` files for complete details on the AWS resources created.
