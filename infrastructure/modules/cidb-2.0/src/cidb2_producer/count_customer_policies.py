#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Count customer IAM policies per AWS account
"""
import sys
import logging
import json
import base64
import gzip
import concurrent.futures
from botocore.exceptions import ClientError
from cidb2_producer import ClientSession, CIDBBase
from circuit_breaker import CircuitBreaker

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(console_handler)

# Create circuit breaker for IAM operations
iam_cb = CircuitBreaker(name="iam-operations", failure_threshold=3, recovery_timeout=30)


def process_account(account_id, role_name, cidb_client):
    """
    Process a single account to count policies and collect ARNs

    Args:
        account_id (str): AWS account ID
        role_name (str): IAM role name to assume
        cidb_client (CIDBBase): CIDB client instance

    Returns:
        tuple: (dict, list) - Account result dict and list of policy ARNs
    """
    policy_arns = []
    policy_count = 0

    if not iam_cb.allow_request():
        logger.warning("Circuit breaker for IAM operations is OPEN, skipping account")
        return {"AWSAccountID": account_id, "TotalIAMCustomerPolicies": 0}, []

    try:
        # Assume role in the account
        assumed_session = cidb_client.assume_role(account_id, role_name)
        if assumed_session:
            # Create IAM client
            iam_client = assumed_session.client("iam")

            # List customer managed policies (Scope='Local')
            paginator = iam_client.get_paginator("list_policies")

            for page in paginator.paginate(Scope="Local"):
                policies = page.get("Policies", [])
                policy_count += len(policies)
                # Extract ARNs in a list comprehension
                policy_arns.extend([p["Arn"] for p in policies if "Arn" in p])

            logger.info(
                f"Account {account_id}: {policy_count} customer managed policies"
            )
            iam_cb.record_success()
        else:
            logger.error(f"Failed to assume role in account {account_id}")
            iam_cb.record_failure(Exception("Failed to assume role"))
    except ClientError as e:
        logger.error(f"Error processing account {account_id}: {str(e)}")
        iam_cb.record_failure(e)
    except Exception as e:
        logger.error(f"Unexpected error processing account {account_id}: {str(e)}")
        iam_cb.record_failure(e)

    # Return result regardless of success/failure
    return {
        "AWSAccountID": account_id,
        "TotalIAMCustomerPolicies": policy_count,
    }, policy_arns


def count_customer_policies_per_account(
    account_ids,
    role_name="sandbox-assumerole-test",
    profile_name="Default",
    max_workers=10,
):
    """
    Count the number of customer IAM policies per AWS account and return compressed policy ARNs

    Args:
        account_ids (list): List of AWS account IDs
        role_name (str): IAM role name to assume in each account
        profile_name (str): AWS profile name to use
        max_workers (int): Maximum number of worker threads

    Returns:
        tuple: (list, dict) - List of dictionaries with account ID and policy count,
               and dictionary with account IDs as keys and compressed policy ARNs as values
    """
    # Create client session
    client_session = ClientSession()
    cidb_client = CIDBBase(client_session=client_session)

    results = []
    policy_arns_by_account = {}

    # Use ThreadPoolExecutor for parallel processing
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(max_workers, len(account_ids))
    ) as executor:
        # Submit all account processing tasks
        future_to_account = {
            executor.submit(
                process_account, account_id, role_name, cidb_client
            ): account_id
            for account_id in account_ids
        }

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_account):
            account_id = future_to_account[future]
            try:
                result, policy_arns = future.result()
                results.append(result)

                # Compress the policy ARNs to reduce payload size
                if policy_arns:
                    json_str = json.dumps(policy_arns)
                    compressed = gzip.compress(json_str.encode("utf-8"))
                    policy_arns_by_account[account_id] = base64.b64encode(
                        compressed
                    ).decode("ascii")
                else:
                    policy_arns_by_account[account_id] = ""

            except Exception as e:
                logger.error(f"Account {account_id} generated an exception: {str(e)}")
                results.append(
                    {"AWSAccountID": account_id, "TotalIAMCustomerPolicies": 0}
                )
                policy_arns_by_account[account_id] = ""

    return results, policy_arns_by_account


def split_accounts_into_slices(
    results, policy_arns_by_account, n_slices=1, max_size_kb=250
):
    """
    Split accounts into n slices, balancing the total number of policies
    and ensuring each slice is under the maximum size limit

    Args:
        results (list): List of dictionaries with account ID and policy count
        policy_arns_by_account (dict): Dictionary with account IDs as keys and compressed policy ARNs as values
        n_slices (int): Initial number of slices to create
        max_size_kb (int): Maximum size of each slice in KB

    Returns:
        list: List of slices, each containing accounts with their compressed ARNs and total policies
    """
    if n_slices <= 0:
        n_slices = 1
    elif n_slices > len(results):
        n_slices = len(results)

    # Sort accounts by policy count in descending order
    sorted_results = sorted(
        results, key=lambda x: x["TotalIAMCustomerPolicies"], reverse=True
    )

    # Initialize slices with new structure
    slices = [{"accounts": {}, "total_policies": 0} for _ in range(n_slices)]

    # Distribute accounts using greedy approach
    for result in sorted_results:
        account_id = result["AWSAccountID"]
        compressed_arns = policy_arns_by_account.get(account_id, "")

        # Find the slice with the minimum total policies
        min_slice = min(slices, key=lambda x: x["total_policies"])

        # Check if adding this account would exceed the size limit
        test_slice = min_slice.copy()
        test_accounts = test_slice["accounts"].copy()
        test_accounts[account_id] = compressed_arns
        test_slice["accounts"] = test_accounts
        test_slice["total_policies"] += result["TotalIAMCustomerPolicies"]

        # Calculate size of the slice
        slice_size_bytes = len(json.dumps(test_slice).encode("utf-8"))
        slice_size_kb = slice_size_bytes / 1024

        # If slice would exceed max size, create a new slice
        if slice_size_kb > max_size_kb:
            logger.info(
                f"Creating new slice as current one would exceed {max_size_kb}KB limit"
            )
            new_slice = {
                "accounts": {account_id: compressed_arns},
                "total_policies": result["TotalIAMCustomerPolicies"],
            }
            slices.append(new_slice)
        else:
            # Add to existing slice
            min_slice["accounts"][account_id] = compressed_arns
            min_slice["total_policies"] += result["TotalIAMCustomerPolicies"]

    # Log slice sizes
    for i, slice_data in enumerate(slices):
        slice_size_kb = len(json.dumps(slice_data).encode("utf-8")) / 1024
        logger.info(
            f"Slice {i+1} size: {slice_size_kb:.2f}KB, policies: {slice_data['total_policies']}"
        )

    return slices


def decompress_slices(compressed_slices):
    """
    Decompress ARNs in slices and recreate the uncompressed structure

    Args:
        compressed_slices (list): List of slices with compressed ARNs

    Returns:
        list: List of slices with decompressed ARNs
    """
    decompressed_slices = []

    for slice_data in compressed_slices:
        decompressed_slice = {
            "accounts": {},
            "total_policies": slice_data["total_policies"],
        }

        for account_id, compressed_arns in slice_data["accounts"].items():
            if compressed_arns:  # Only decompress if there's data
                try:
                    # Decode base64 and decompress
                    binary_data = base64.b64decode(compressed_arns)
                    decompressed_data = gzip.decompress(binary_data).decode("utf-8")
                    arns_list = json.loads(decompressed_data)
                    decompressed_slice["accounts"][account_id] = arns_list
                except Exception as e:
                    logger.error(
                        f"Error decompressing ARNs for account {account_id}: {str(e)}"
                    )
                    decompressed_slice["accounts"][account_id] = []
            else:
                decompressed_slice["accounts"][account_id] = []

        decompressed_slices.append(decompressed_slice)

    return decompressed_slices
