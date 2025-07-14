import logging
import sys
from botocore.exceptions import ClientError
from circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from cidb2_producer import CIDBBase, SnsPublisher, CIDBConfig
from common_functions import extract_error_code

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(console_handler)


class CloudWatchClient:
    def __init__(self, client: CIDBBase):
        self.client = client
        self.params = CIDBConfig
        self.cloudwatch_cb = CircuitBreaker(
            name="cloudwatch-operations", failure_threshold=3, recovery_timeout=30
        )

    def get_alarms_for_region(self, region_name=None, account_id=None, role_name=None):
        """
        Get all CloudWatch alarms for a specific region

        Args:
            region_name (str): AWS region name
            account_id (str, optional): AWS account ID for cross-account operations
            role_name (str, optional): IAM role name to assume for cross-account operations

        Returns:
            dict: Dictionary with alarm details and status
        """
        if not self.cloudwatch_cb.allow_request():
            logger.warning(
                "Circuit breaker for CloudWatch operations is OPEN, fast failing"
            )
            raise CircuitBreakerOpenError(
                "Circuit breaker for CloudWatch operations is OPEN"
            )

        try:
            # Get appropriate client
            if account_id and role_name:
                try:
                    assumed_session = self.client.assume_role(account_id, role_name)
                    if not assumed_session:
                        raise Exception(
                            f"Failed to assume role in account {account_id}"
                        )
                    cloudwatch_client = assumed_session.client(
                        "cloudwatch", region_name=region_name
                    )
                except Exception as e:
                    logger.error(
                        f"Error assuming role in account {account_id}: {str(e)}"
                    )
                    self.cloudwatch_cb.record_failure(e)
                    raise
            else:
                cloudwatch_client = self.client.get_client(
                    "cloudwatch", region_name=region_name
                )

            # Get all alarms
            alarms = {}
            paginator = cloudwatch_client.get_paginator("describe_alarms")

            for page in paginator.paginate():
                for alarm in page.get("MetricAlarms", []):
                    alarm_name = alarm.get("AlarmName")
                    alarm_arn = alarm.get("AlarmArn")
                    # Get tags for the alarm
                    formatted_tags = []
                    try:
                        tags_response = cloudwatch_client.list_tags_for_resource(
                            ResourceARN=alarm_arn
                        )
                        tags = tags_response.get("Tags", [])
                        # Convert tags to our standard format
                        if isinstance(tags, list):
                            for tag in tags:
                                if "Key" in tag and "Value" in tag:
                                    formatted_tags.append(
                                        {"TagKey": tag["Key"], "TagValue": tag["Value"]}
                                    )
                        # Or it might return as a dict {key: value}
                        elif isinstance(tags, dict):
                            for key, value in tags.items():
                                formatted_tags.append(
                                    {"TagKey": key, "TagValue": value}
                                )
                    except ClientError as e:
                        logger.warning(
                            f"Could not get tags for alarm {alarm_name}: {str(e)}"
                        )
                        tags = []

                    # Determine if AWS managed
                    is_aws_managed = False
                    if alarm_name.startswith("AWS_") or alarm_name.startswith(
                        "AwsManaged"
                    ):
                        is_aws_managed = True

                    # Store alarm details
                    alarms[alarm_name] = {
                        "AlarmName": alarm_name,
                        "Arn": alarm_arn,
                        "Tags": formatted_tags,
                        "IsAwsManaged": is_aws_managed,
                    }

            self.cloudwatch_cb.record_success()
            return {"status": "success", "data": alarms}

        except Exception as e:
            self.cloudwatch_cb.record_failure(e)
            logger.error(f"Error getting CloudWatch alarms: {str(e)}")
            return {"status": "failed", "error": str(e)}

    def get_all_service_tags_multi_account(self, accounts_config):
        """
        Get all CloudWatch alarms across multiple accounts and regions

        Args:
            accounts_config (list): List of dictionaries with account_id, role_name, and regions
                [{'account_id': '123456789012', 'role_name': 'MyRole', 'regions': ['us-east-1']}, ...]

        Returns:
            dict: Results with account and region level information
        """
        results = {"results": {}}
        successful_accounts = 0
        failed_accounts = 0
        skipped_accounts = 0

        for account in accounts_config:
            account_id = account.get("account_id")
            role_name = account.get("role_name")
            regions = account.get("regions", [])

            if not account_id or not role_name or not regions:
                logger.warning(f"Skipping invalid account config: {account}")
                continue

            try:
                account_results = {"regions": {}, "status": "success"}

                for region in regions:
                    try:
                        logger.info(f"Processing account {account_id}, region {region}")
                        region_results = self.get_alarms_for_region(
                            region_name=region,
                            account_id=account_id,
                            role_name=role_name,
                        )
                        account_results["regions"][region] = region_results
                    except CircuitBreakerOpenError as e:
                        logger.warning(
                            f"Circuit breaker open for region {region}: {str(e)}"
                        )
                        account_results["regions"][region] = {
                            "status": "skipped",
                            "error": "Circuit breaker open",
                        }
                    except Exception as e:
                        logger.error(f"Error processing region {region}: {str(e)}")
                        account_results["regions"][region] = {
                            "status": "failed",
                            "error": str(e),
                        }

                results["results"][account_id] = account_results
                successful_accounts += 1

            except CircuitBreakerOpenError as e:
                logger.warning(
                    f"Circuit breaker open for account {account_id}: {str(e)}"
                )
                results["results"][account_id] = {
                    "regions": {},
                    "error": "Circuit breaker open",
                    "status": "skipped",
                }
                failed_accounts += 1

                for remaining_account in accounts_config:
                    remaining_id = remaining_account.get("account_id")
                    if remaining_id and remaining_id not in results["results"]:
                        results["results"][remaining_id] = {
                            "regions": {},
                            "error": "Operation skipped due to circuit breaker",
                            "status": "skipped",
                        }
                        skipped_accounts += 1
                break

            except Exception as e:
                logger.error(f"Error processing account {account_id}: {str(e)}")
                results["results"][account_id] = {
                    "regions": {},
                    "error": str(e),
                    "status": "failed",
                }
                failed_accounts += 1

        results["metadata"] = {
            "total_accounts": len(accounts_config),
            "successful_accounts": successful_accounts,
            "failed_accounts": failed_accounts,
            "skipped_accounts": skipped_accounts,
        }

        return results
