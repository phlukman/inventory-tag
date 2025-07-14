import sys
import logging
from botocore.exceptions import ClientError
from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from cidb2_producer import ClientSession, CIDBBase, SnsPublisher, CIDBConfig
from common_functions import (
    convert_results_to_csv_format,
    write_csv_data_to_s3,
    extract_error_code,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
# Handler para consola
console_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(console_handler)


class CassandraClient:
    def __init__(self, client: CIDBBase):
        self.client = client
        self.params = CIDBConfig
        # Create circuit breakers for Cassandra operations
        self.cassandra_cb = CircuitBreaker(
            name="cassandra-operations", failure_threshold=3, recovery_timeout=30
        )

    def get_all_keyspaces(self, region_name=None, account_id=None, role_name=None):
        """
        Get all Cassandra keyspaces and their tags for an account and region.

        Args:
            region_name (str, optional): AWS region name. Defaults to None.
            account_id (str, optional): AWS account ID for cross-account operations. Defaults to None.
            role_name (str, optional): IAM role name to assume for cross-account operations. Defaults to None.

        Returns:
            dict: Dictionary mapping keyspace names to their ARNs and tags
        """
        if not self.cassandra_cb.allow_request():
            logger.warning(
                "Circuit breaker for Cassandra operations is OPEN, fast failing"
            )
            raise CircuitBreakerOpenError(
                "Circuit breaker for Cassandra operations is OPEN"
            )

        try:
            # Get appropriate Cassandra client
            if account_id and role_name:
                try:
                    assumed_session = self.client.assume_role(account_id, role_name)
                    if not assumed_session:
                        raise Exception(
                            f"Failed to assume role in account {account_id}"
                        )
                    keyspaces_client = assumed_session.client(
                        "keyspaces", region_name=region_name
                    )
                    resourcegroupstaggingapi_client = assumed_session.client(
                        "resourcegroupstaggingapi", region_name=region_name
                    )
                except Exception as e:
                    logger.error(
                        f"Error assuming role in account {account_id}: {str(e)}"
                    )
                    self.cassandra_cb.record_failure(e)
                    raise
            else:
                keyspaces_client = self.client.get_client(
                    "keyspaces", region_name=region_name
                )
                resourcegroupstaggingapi_client = self.client.get_client(
                    "resourcegroupstaggingapi", region_name=region_name
                )

            results = {}

            # Get all keyspaces
            try:
                paginator = keyspaces_client.get_paginator("list_keyspaces")
                for page in paginator.paginate():
                    for keyspace in page.get("keyspaces", []):
                        keyspace_name = keyspace.get("keyspaceName")
                        # Skip system keyspaces
                        if keyspace_name.startswith("system"):
                            continue
                        # Construct ARN - Cassandra keyspace ARNs follow this pattern
                        keyspace_arn = f"arn:aws:cassandra:{region_name}:{account_id}:/keyspace/{keyspace_name}/"

                        # Get tags for the keyspace using ResourceGroupsTaggingAPI
                        try:
                            tags_response = (
                                resourcegroupstaggingapi_client.get_resources(
                                    ResourceARNList=[keyspace_arn],
                                )
                            )

                            # Extract tags from response
                            tags = []
                            for resource in tags_response.get(
                                "ResourceTagMappingList", []
                            ):
                                if resource.get("ResourceARN") == keyspace_arn:
                                    for tag in resource.get("Tags", []):
                                        tags.append(
                                            {
                                                "TagKey": tag.get("Key"),
                                                "TagValue": tag.get("Value"),
                                            }
                                        )
                        except ClientError as e:
                            error_code, error_message = extract_error_code(e)
                            logger.warning(
                                f"Could not get tags for keyspace {keyspace_name}: {error_code} - {error_message}"
                            )
                            tags = []

                        # Store keyspace details
                        results[keyspace_name] = {
                            "KeyspaceName": keyspace_name,
                            "Arn": keyspace_arn,
                            "Tags": tags,
                        }
            except ClientError as e:
                error_code, error_message = extract_error_code(e)
                logger.error(f"Error listing keyspaces: {error_code} - {error_message}")
                raise

            self.cassandra_cb.record_success()
            return results

        except Exception as e:
            self.cassandra_cb.record_failure(e)
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", str(e))
            error_message = (
                getattr(e, "response", {}).get("Error", {}).get("Message", str(e))
            )
            account_info = f" in account {account_id}" if account_id else ""
            region_info = f" in region {region_name}" if region_name else ""
            logger.error(
                f"Error getting Cassandra keyspaces{account_info}{region_info}: {error_code} - {error_message}"
            )
            raise

    def get_all_service_tags_multi_account(self, accounts_config):
        """
        Get all Cassandra keyspaces across multiple accounts and regions.

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
            account_regions = account.get("regions", [None])

            if not account_id or not role_name:
                logger.warning(f"Skipping invalid account config: {account}")
                skipped_accounts += 1
                continue

            try:
                account_results = {"regions": {}, "status": "success"}

                for region in account_regions:
                    try:
                        region_results = self.get_all_keyspaces(
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
