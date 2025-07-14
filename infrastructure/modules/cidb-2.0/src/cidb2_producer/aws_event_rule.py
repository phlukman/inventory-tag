import sys
import logging
from botocore.exceptions import ClientError

from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from cidb2_producer import CIDBBase, SnsPublisher, CIDBConfig
from common_functions import extract_error_code

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
# Handler for console
console_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(console_handler)


class EventBridgeClient:
    def __init__(self, client: CIDBBase):
        self.client = client
        self.params = CIDBConfig
        # Create circuit breakers for EventBridge operations
        self.events_cb = CircuitBreaker(
            name="events-operations", failure_threshold=3, recovery_timeout=30
        )

    def get_all_rules(self, region_name=None, account_id=None, role_name=None):
        """
        Get all EventBridge rules and their tags for an account and region.

        Args:
            region_name (str, optional): AWS region name. Defaults to None.
            account_id (str, optional): AWS account ID for cross-account operations. Defaults to None.
            role_name (str, optional): IAM role name to assume for cross-account operations. Defaults to None.

        Returns:
            dict: Dictionary mapping rule names to their ARNs and tags
        """
        if not self.events_cb.allow_request():
            logger.warning(
                "Circuit breaker for EventBridge operations is OPEN, fast failing"
            )
            raise CircuitBreakerOpenError(
                "Circuit breaker for EventBridge operations is OPEN"
            )

        try:
            # Get appropriate EventBridge client
            if account_id and role_name:
                try:
                    assumed_session = self.client.assume_role(account_id, role_name)
                    if not assumed_session:
                        raise Exception(
                            f"Failed to assume role in account {account_id}"
                        )
                    events_client = assumed_session.client(
                        "events", region_name=region_name
                    )
                except Exception as e:
                    logger.error(
                        f"Error assuming role in account {account_id}: {str(e)}"
                    )
                    self.events_cb.record_failure(e)
                    raise
            else:
                events_client = self.client.get_client(
                    "events", region_name=region_name
                )

            results = {}
            paginator = events_client.get_paginator("list_rules")

            for page in paginator.paginate():
                for rule in page.get("Rules", []):
                    rule_name = rule.get("Name")
                    rule_arn = rule.get("Arn")
                    is_aws_managed = (
                        rule_name.startswith("AWS.") if rule_name else False
                    )

                    # Get tags for the rule
                    try:
                        tags_response = events_client.list_tags_for_resource(
                            ResourceARN=rule_arn
                        )
                        tags = tags_response.get("Tags", [])

                        # Convert tags to our standard format
                        formatted_tags = []
                        # EventBridge returns tags as a list of {'Key': key, 'Value': value} dictionaries
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

                        results[rule_name] = {
                            "Arn": rule_arn,
                            "Tags": formatted_tags,
                            "IsAwsManaged": is_aws_managed,
                        }
                    except ClientError as e:
                        error_code, error_message = extract_error_code(e)
                        logger.warning(
                            f"Could not get tags for rule {rule_name}: {error_code} - {error_message}"
                        )
                        results[rule_name] = {
                            "Arn": rule_arn,
                            "Tags": [],
                            "IsAwsManaged": is_aws_managed,
                            "error": f"{error_code}: {error_message}",
                        }

            self.events_cb.record_success()
            return results

        except Exception as e:
            self.events_cb.record_failure(e)
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", str(e))
            error_message = (
                getattr(e, "response", {}).get("Error", {}).get("Message", str(e))
            )
            account_info = f" in account {account_id}" if account_id else ""
            region_info = f" in region {region_name}" if region_name else ""
            logger.error(
                f"Error getting EventBridge rules{account_info}{region_info}: {error_code} - {error_message}"
            )
            raise

    def get_all_service_tags_multi_account(self, accounts_config):
        """
        Get all EventBridge rules across multiple accounts and regions.

        Args:
            accounts_config (list): List of dictionaries with account_id, role_name, and regions
                [{'account_id': '123456789012', 'role_name': 'MyRole', 'regions': ['us-east-1', 'us-west-2']}, ...]

        Returns:
            dict: Dictionary with results and metadata
        """
        results = {"results": {}, "metadata": {}}
        successful_accounts = 0
        failed_accounts = 0
        skipped_accounts = 0

        for account in accounts_config:
            account_id = account.get("account_id")
            role_name = account.get("role_name")
            account_regions = account.get(
                "regions", [None]
            )  # Default to [None] to use default region

            if not account_id or not role_name:
                logger.warning(f"Skipping invalid account config: {account}")
                skipped_accounts += 1
                continue

            try:
                account_results = {"regions": {}, "status": "success"}

                for region in account_regions:
                    try:
                        region_results = self.get_all_rules(
                            region_name=region,
                            account_id=account_id,
                            role_name=role_name,
                        )
                        region_key = region if region else "default"
                        account_results["regions"][region_key] = {
                            "data": region_results,
                            "status": "success",
                            "error": None,
                        }
                    except Exception as e:
                        region_key = region if region else "default"
                        logger.error(
                            f"Error processing region {region_key} in account {account_id}: {str(e)}"
                        )
                        account_results["regions"][region_key] = {
                            "data": None,
                            "error": str(e),
                            "status": "failed",
                        }

                results["results"][account_id] = account_results
                successful_accounts += 1

            except CircuitBreakerOpenError as e:
                logger.warning(
                    f"Circuit breaker open, stopping multi-account processing: {str(e)}"
                )
                results["results"][account_id] = {
                    "regions": {},
                    "error": str(e),
                    "status": "failed",
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
