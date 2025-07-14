#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
common_functions.py
This module provides utility functions for processing AWS service data, converting results to CSV format, uploading CSV data to Amazon S3, generating service tags inventory, and decompressing compressed data slices.
Functions:
- extract_error_code(error):
    Extracts the error code and message from a boto3 ClientError exception.
- convert_results_to_csv_format(results, service_type, exclude_aws_managed=False):
    Converts service results into a list of dictionaries suitable for CSV export, with options to exclude AWS managed rules.
- write_csv_data_to_s3(csv_data, bucket_name, object_key, region=None, profile_name=None):
    Writes a list of dictionaries as CSV data to an S3 bucket.
- generate_service_tags_inventory(service_client, accounts_config, bucket_name, object_key, service_type, profile_name=None):
    Retrieves service tags inventory across multiple AWS accounts, converts the results to CSV, and uploads the file to S3.
- decompress_slices(slice_data):
    Decompresses base64-encoded and gzip-compressed ARNs in a data slice and returns the decompressed data structure.
"""

import json
import csv
import io
import logging
import sys
import base64
import gzip
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(console_handler)


# Helper function for extracting error details
def extract_error_code(error):
    """Extract error code and message from a ClientError"""
    if isinstance(error, ClientError):
        error_code = error.response.get("Error", {}).get("Code", "Unknown")
        error_message = error.response.get("Error", {}).get("Message", "")
        return error_code, error_message
    return "Unknown", str(error)


def convert_results_to_csv_format(results, service_type, exclude_aws_managed=False):
    """
    Convert generic service results to CSV format with specified headers

    Args:
        results (dict): Results from get_all_rules_multi_account
        exclude_aws_managed (bool): Whether to exclude AWS managed rules

    Returns:
        list: List of dictionaries with CSV format
    """
    csv_data = []

    for account_id, account_data in results["results"].items():
        if account_data.get("status") != "success":
            continue

        for region, region_info in account_data["regions"].items():
            if region_info.get("status") != "success" or not region_info.get("data"):
                continue

            for rule_name, rule_info in region_info["data"].items():
                # Skip AWS managed rules if exclude_aws_managed is True
                if exclude_aws_managed and rule_info.get("IsAwsManaged", False):
                    continue

                # Format tags as JSON string
                tags_dict = {}
                for tag in rule_info.get("Tags", []):
                    if "TagKey" in tag and "TagValue" in tag:
                        tags_dict[tag["TagKey"]] = tag["TagValue"]
                tags_json = json.dumps(tags_dict).replace('"', "'")
                # Create CSV row
                csv_row = {
                    "Type": service_type,
                    "AWSAccountId": account_id,
                    "ARN": rule_info.get("Arn", ""),
                    "Tags": tags_json or "{}",
                }

                csv_data.append(csv_row)

    return csv_data


def write_csv_data_to_s3(
    csv_data, bucket_name, object_key, region=None, profile_name=None
):
    """
    Write CSV data to S3

    Args:
        csv_data (list): List of dictionaries to write as CSV
        bucket_name (str): S3 bucket name
        object_key (str): S3 object key
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name

    Returns:
        dict: Result of the operation
    """
    try:
        # Create session and client
        if profile_name:
            session = boto3.Session(profile_name=profile_name, region_name=region)
        else:
            session = boto3.Session(region_name=region)

        s3_client = session.client("s3")

        # Create CSV in memory
        csv_buffer = io.StringIO()
        headers = ["Type", "AWSAccountId", "ARN", "Tags"]

        writer = csv.DictWriter(csv_buffer, fieldnames=headers)
        writer.writeheader()

        for row in csv_data:
            writer.writerow(
                {
                    "Type": row.get("Type", ""),
                    "AWSAccountId": row.get("AWSAccountId", ""),
                    "ARN": row.get("ARN", ""),
                    "Tags": row.get("Tags", "{}"),
                }
            )

        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=csv_buffer.getvalue(),
            ContentType="text/csv",
        )

        logger.info(
            f"Successfully wrote {len(csv_data)} rows to s3://{bucket_name}/{object_key}"
        )

        return {
            "status": "success",
            "bucket": bucket_name,
            "key": object_key,
            "rows": len(csv_data),
        }

    except Exception as e:
        logger.error(f"Error writing to S3: {str(e)}")
        return {"status": "error", "message": str(e)}


def generate_service_tags_inventory(
    service_client,
    accounts_config,
    bucket_name,
    object_key,
    service_type,
    profile_name=None,
):

    try:
        # Get all rules across specified accounts and regions
        results = service_client.get_all_service_tags_multi_account(
            accounts_config=accounts_config,
        )

        # Log metadata
        metadata = results["metadata"]
        logger.info("\nExecution Summary:")
        logger.info(f"Total accounts: {metadata['total_accounts']}")
        logger.info(f"Successful accounts: {metadata['successful_accounts']}")
        logger.info(f"Failed accounts: {metadata['failed_accounts']}")
        logger.info(f"Skipped accounts: {metadata['skipped_accounts']}")

        # Convert results to CSV format, excluding AWS managed rules
        csv_data = convert_results_to_csv_format(
            results, service_type, exclude_aws_managed=True
        )
        # Write to S3 - file without AWS managed rules
        s3_result = write_csv_data_to_s3(
            csv_data=csv_data,
            bucket_name=bucket_name,
            object_key=object_key,
            profile_name=profile_name,
        )

        # Log results file
        if s3_result["status"] == "success":
            logger.info(
                f"\nSuccessfully uploaded {service_type} CSV to S3: s3://{s3_result['bucket']}/{s3_result['key']}"
            )
            logger.info(f"Total {service_type}: {s3_result['rows']}")
        else:
            logger.info(
                f"\nFailed to upload {service_type} CSV to S3: {s3_result['message']}"
            )

    except Exception as e:
        logger.error(f"Error retrieving {service_type}: {str(e)}")


def decompress_slices(slice_data):
    """
    Decompress ARNs in a single slice

    Args:
        slice_data (dict): Single slice with compressed ARNs

    Returns:
        dict: Slice with decompressed ARNs
    """
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

    return decompressed_slice
