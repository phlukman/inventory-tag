import sys
import logging
from dataclasses import dataclass
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
# Handler para consola
console_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(console_handler)


class AppConfigClient:
    def __init__(self, client: CIDBBase):
        self.client = client
        self.params = CIDBConfig
        # Create circuit breakers for AppConfig operations
        self.appconfig_cb = CircuitBreaker(
            name="appconfig-operations", failure_threshold=3, recovery_timeout=30
        )

    def get_all_deployment_strategy(
        self, region_name=None, account_id=None, role_name=None
    ):
        """
        Get all AppConfig deployment strategy and their tags for a specific region

        Args:
            region_name (str): AWS region name
            account_id (str, optional): AWS account ID for cross-account operations. Defaults to None.
            role_name (str, optional): IAM role name to assume for cross-account operations. Defaults to None.

        Returns:
            dict: Dictionary mapping strategy IDs to their details and tags
        """
        if not self.appconfig_cb.allow_request():
            logger.warning(
                "Circuit breaker for AppConfig operations is OPEN, fast failing"
            )
            raise CircuitBreakerOpenError(
                "Circuit breaker for AppConfig operations is OPEN"
            )

        try:
            # Get appropriate AppConfig client
            if account_id and role_name:
                try:
                    assumed_session = self.client.assume_role(account_id, role_name)
                    if not assumed_session:
                        raise Exception(
                            f"Failed to assume role in account {account_id}"
                        )
                    appconfig_client = assumed_session.client(
                        "appconfig", region_name=region_name
                    )
                except Exception as e:
                    logger.error(
                        f"Error assuming role in account {account_id}: {str(e)}"
                    )
                    self.appconfig_cb.record_failure(e)
                    raise
            else:
                appconfig_client = self.client.get_client(
                    "appconfig", region_name=region_name
                )

            results = {}

            # Get all deployment strategy
            try:
                paginator = appconfig_client.get_paginator("list_deployment_strategies")
                for page in paginator.paginate():
                    for strategy in page.get("Items", []):
                        strategy_id = strategy.get("Id")
                        strategy_name = strategy.get("Name")

                        # Construct ARN - AppConfig deployment strategy ARNs follow this pattern
                        strategy_arn = f"arn:aws:appconfig:{region_name}:{account_id}:deploymentstrategy/{strategy_id}"

                        # Get tags for the deployment strategy
                        try:
                            tags_response = appconfig_client.list_tags_for_resource(
                                ResourceArn=strategy_arn
                            )

                            # Convert to standard tag format
                            tags = []
                            for key, value in tags_response.get("Tags", {}).items():
                                tags.append({"TagKey": key, "TagValue": value})
                        except ClientError as e:
                            error_code, error_message = extract_error_code(e)
                            logger.warning(
                                f"Could not get tags for deployment strategy {strategy_id}: {error_code} - {error_message}"
                            )
                            tags = []

                        # Determine if AWS managed
                        is_aws_managed = False
                        if strategy_name and strategy_name.startswith("AWS."):
                            is_aws_managed = True

                        # Store strategy details
                        results[strategy_id] = {
                            "Id": strategy_id,
                            "Arn": strategy_arn,
                            "Tags": tags,
                            "IsAwsManaged": is_aws_managed,
                        }
            except ClientError as e:
                error_code, error_message = extract_error_code(e)
                logger.error(
                    f"Error listing deployment strategy: {error_code} - {error_message}"
                )
                raise

            self.appconfig_cb.record_success()
            return results

        except Exception as e:
            self.appconfig_cb.record_failure(e)
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", str(e))
            error_message = (
                getattr(e, "response", {}).get("Error", {}).get("Message", str(e))
            )
            account_info = f" in account {account_id}" if account_id else ""
            region_info = f" in region {region_name}" if region_name else ""
            logger.error(
                f"Error getting AppConfig deployment strategy{account_info}{region_info}: {error_code} - {error_message}"
            )
            raise

    def get_all_service_tags_multi_account(self, accounts_config):
        """
        Get all AppConfig deployment strategy across multiple accounts and regions

        Args:
            accounts_config (list): List of dictionaries with account_id, role_name, and regions
                [{'account_id': '123456789012', 'role_name': 'MyRole', 'regions': ['us-east-1']}, ...]

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
            regions = account.get("regions", [])

            if not account_id or not role_name or not regions:
                logger.warning(f"Skipping invalid account config: {account}")
                skipped_accounts += 1
                continue

            try:
                account_results = {"regions": {}, "status": "success"}

                for region in regions:
                    try:
                        logger.info(f"Processing account {account_id}, region {region}")
                        region_results = self.get_all_deployment_strategy(
                            region_name=region,
                            account_id=account_id,
                            role_name=role_name,
                        )
                        account_results["regions"][region] = {
                            "data": region_results,
                            "status": "success",
                            "error": None,
                        }
                    except CircuitBreakerOpenError as e:
                        logger.warning(
                            f"Circuit breaker open for region {region}: {str(e)}"
                        )
                        account_results["regions"][region] = {
                            "data": None,
                            "status": "skipped",
                            "error": "Circuit breaker open",
                        }
                    except Exception as e:
                        logger.error(f"Error processing region {region}: {str(e)}")
                        account_results["regions"][region] = {
                            "data": None,
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
