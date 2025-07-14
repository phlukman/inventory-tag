#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Save tags to SQS queue for a list of AWS services

A script for lambda to save tags to SQS queue for a list of AWS services

"""
"""
Count customer IAM policies per AWS account
"""
import logging
import concurrent.futures
import sys
from os import environ as env
from cidb2_producer import CIDBBase, SnsPublisher, CIDBConfig
from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerDecorator,
    CircuitBreakerOpenError,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
# Handler for console
console_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(console_handler)


class IAMPolicyClient:
    def __init__(self, client: CIDBBase, assume_role):
        self.client = client
        self.params = CIDBConfig
        self.assume_role = assume_role
        # Create circuit breakers for IAM operations
        self.assume_role_cb = CircuitBreaker(
            name="assume-role", failure_threshold=3, recovery_timeout=60
        )
        self.iam_cb = CircuitBreaker(
            name="iam-operations", failure_threshold=5, recovery_timeout=30
        )

    def list_policy_properties_from_slice(self, slice_data, max_workers=5):
        """
        List IAM policies with their properties from a slice data structure

        Args:
            slice_data (dict): Slice with accounts and their policy ARNs
            max_workers (int): Maximum number of concurrent workers

        Returns:
            dict: Dictionary containing policies and statistics
        """
        try:
            all_policies = []
            account_results = {}

            # Fallback functions
            def assume_role_fallback(account_id):
                logger.warning(
                    f"Circuit breaker fallback for assume role: {account_id}"
                )
                return None

            def iam_fallback():
                logger.warning("Circuit breaker fallback for IAM operations")
                return {}

            # Create decorators
            assume_role_decorator = CircuitBreakerDecorator(
                self.assume_role_cb, assume_role_fallback
            )
            iam_decorator = CircuitBreakerDecorator(self.iam_cb, iam_fallback)

            @assume_role_decorator
            def assume_role_with_cb(account_id):
                assumed_session = self.client.assume_role(account_id, self.assume_role)
                if assumed_session:
                    self.assume_role_cb.record_success()
                    return assumed_session
                else:
                    self.assume_role_cb.record_failure(
                        Exception("Failed to assume role")
                    )
                    return None

            @iam_decorator
            def get_policy_with_cb(iam_client, policy_arn):
                try:
                    policy_response = iam_client.get_policy(PolicyArn=policy_arn)
                    tags_response = iam_client.list_policy_tags(PolicyArn=policy_arn)
                    self.iam_cb.record_success()
                    return policy_response, tags_response
                except Exception as e:
                    self.iam_cb.record_failure(e)
                    raise

            def process_account_policies(account_id, policy_arns):
                """Process policies for a single account"""
                if not self.assume_role_cb.allow_request():
                    logger.warning(
                        f"Circuit breaker OPEN for assume role, skipping account {account_id}"
                    )
                    return []

                try:
                    # Assume role with circuit breaker
                    assumed_session = assume_role_with_cb(account_id)
                    if not assumed_session:
                        return []

                    # Create IAM client
                    iam_client = assumed_session.client("iam")

                    policies = []
                    for policy_arn in policy_arns:
                        if not self.iam_cb.allow_request():
                            logger.warning(
                                f"Circuit breaker OPEN for IAM operations, skipping policy {policy_arn}"
                            )
                            continue

                        try:
                            # Get policy details with circuit breaker
                            policy_response, tags_response = get_policy_with_cb(
                                iam_client, policy_arn
                            )
                            policy = policy_response.get("Policy", {})
                            tags = {
                                tag["Key"]: tag["Value"]
                                for tag in tags_response.get("Tags", [])
                            }

                            policy_properties = {
                                "AccountId": account_id,
                                "PolicyArn": policy_arn,
                                "PolicyName": policy.get("PolicyName", ""),
                                "Tags": tags,
                            }

                            policies.append(policy_properties)

                        except Exception as e:
                            logger.error(
                                f"Error processing policy {policy_arn}: {str(e)}"
                            )

                    return policies

                except Exception as e:
                    logger.error(f"Error processing account {account_id}: {str(e)}")
                    return []

            # Process accounts concurrently
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers
            ) as executor:
                future_to_account = {
                    executor.submit(
                        process_account_policies, account_id, policy_arns
                    ): account_id
                    for account_id, policy_arns in slice_data["accounts"].items()
                    if policy_arns  # Only process accounts with policies
                }

                for future in concurrent.futures.as_completed(future_to_account):
                    account_id = future_to_account[future]
                    try:
                        policies = future.result()
                        account_results[account_id] = {
                            "account_id": account_id,
                            "status": "success",
                            "policies": policies,
                            "statistics": {
                                "total": len(policies),
                                "tagged": sum(1 for p in policies if p.get("Tags")),
                                "untagged": sum(
                                    1 for p in policies if not p.get("Tags")
                                ),
                            },
                        }
                        all_policies.extend(policies)
                    except Exception as e:
                        logger.error(
                            f"Error processing future for account {account_id}: {str(e)}"
                        )
                        account_results[account_id] = {
                            "account_id": account_id,
                            "status": "failed",
                            "error": str(e),
                            "policies": [],
                        }

            # Calculate overall statistics
            total_policies = len(all_policies)
            tagged_policies = sum(1 for p in all_policies if p.get("Tags"))

            return {
                "accounts": account_results,
                "all_policies": all_policies,
                "summary": {
                    "total_accounts": len(slice_data["accounts"]),
                    "total_policies": total_policies,
                    "tagged_policies": tagged_policies,
                    "untagged_policies": total_policies - tagged_policies,
                    "tagging_percentage": (
                        (tagged_policies / total_policies * 100)
                        if total_policies > 0
                        else 0
                    ),
                },
                "circuit_breaker_states": {
                    "assume_role": self.assume_role_cb.get_state(),
                    "iam_operations": self.iam_cb.get_state(),
                },
            }

        except Exception as e:
            logger.error(f"Error in list_policy_properties_from_slice: {str(e)}")
            return {
                "accounts": {},
                "all_policies": [],
                "summary": {"total_accounts": 0, "total_policies": 0, "error": str(e)},
            }
