import sys
import logging
from botocore.exceptions import ClientError
from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from cidb2_producer import CIDBBase, SnsPublisher, CIDBConfig
from common_functions import extract_error_code

# -------------------------------------------
# Global variables
# -------------------------------------------
# Write to S3 - file without AWS managed hosted zones

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
# Handler para consola
console_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(console_handler)


class Route53Client:
    def __init__(self, client: CIDBBase):
        self.client = client
        self.params = CIDBConfig
        # Create circuit breakers for Route53 operations
        self.route53_cb = CircuitBreaker(
            name="route53-operations", failure_threshold=3, recovery_timeout=30
        )

    def get_all_hosted_zones(self, account_id=None, role_name=None):
        """
        Get all Route53 hosted zones and their tags for an account.
        Route53 is a global service, so no region parameter is needed.

        Args:
            account_id (str, optional): AWS account ID for cross-account operations. Defaults to None.
            role_name (str, optional): IAM role name to assume for cross-account operations. Defaults to None.

        Returns:
            dict: Dictionary mapping hosted zone IDs to their details and tags
        """
        if not self.route53_cb.allow_request():
            logger.warning(
                "Circuit breaker for Route53 operations is OPEN, fast failing"
            )
            raise CircuitBreakerOpenError(
                "Circuit breaker for Route53 operations is OPEN"
            )

        try:
            # Get appropriate Route53 client
            if account_id and role_name:
                try:
                    assumed_session = self.client.assume_role(account_id, role_name)
                    if not assumed_session:
                        raise Exception(
                            f"Failed to assume role in account {account_id}"
                        )
                    route53_client = assumed_session.client("route53")
                except Exception as e:
                    logger.error(
                        f"Error assuming role in account {account_id}: {str(e)}"
                    )
                    self.route53_cb.record_failure(e)
                    raise
            else:
                route53_client = self.client.get_client("route53")

            results = {}
            paginator = route53_client.get_paginator("list_hosted_zones")

            for page in paginator.paginate():
                for zone in page.get("HostedZones", []):
                    zone_id = zone.get("Id")
                    zone_name = zone.get("Name")
                    formatted_tags = []
                    # Clean up zone_id by removing /hostedzone/ prefix
                    if zone_id and zone_id.startswith("/hostedzone/"):
                        zone_id = zone_id[12:]  # Remove /hostedzone/ prefix

                    # Construct ARN - Route53 hosted zone ARNs follow this pattern
                    zone_arn = f"arn:aws:route53:::hostedzone/{zone_id}"

                    # Get tags for the hosted zone
                    try:
                        tags_response = route53_client.list_tags_for_resource(
                            ResourceType="hostedzone", ResourceId=zone_id
                        )
                        tags = tags_response.get("ResourceTagSet", {}).get("Tags", [])
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
                        error_code, error_message = extract_error_code(e)
                        logger.warning(
                            f"Could not get tags for hosted zone {zone_id}: {error_code} - {error_message}"
                        )
                        tags = []

                    # Store hosted zone details
                    results[zone_id] = {
                        "ZoneId": zone_id,
                        "ZoneName": zone_name,
                        "Arn": zone_arn,
                        "Tags": formatted_tags,
                    }

            self.route53_cb.record_success()
            return results

        except Exception as e:
            self.route53_cb.record_failure(e)
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", str(e))
            error_message = (
                getattr(e, "response", {}).get("Error", {}).get("Message", str(e))
            )
            account_info = f" in account {account_id}" if account_id else ""
            logger.error(
                f"Error getting Route53 hosted zones{account_info}: {error_code} - {error_message}"
            )
            raise

    def get_all_service_tags_multi_account(self, accounts_config):
        """
        Get all Route53 hosted zones across multiple accounts.

        Args:
            accounts_config (list): List of dictionaries with account_id and role_name
                [{'account_id': '123456789012', 'role_name': 'MyRole'}, ...]

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

            if not account_id or not role_name:
                logger.warning(f"Skipping invalid account config: {account}")
                skipped_accounts += 1
                continue

            try:
                account_results = {"regions": {"global": {}}, "status": "success"}

                try:
                    hosted_zones = self.get_all_hosted_zones(
                        account_id=account_id,
                        role_name=role_name,
                    )
                    account_results["regions"]["global"] = {
                        "data": hosted_zones,
                        "status": "success",
                        "error": None,
                    }
                except Exception as e:
                    logger.error(f"Error processing account {account_id}: {str(e)}")
                    account_results["regions"]["global"] = {
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
