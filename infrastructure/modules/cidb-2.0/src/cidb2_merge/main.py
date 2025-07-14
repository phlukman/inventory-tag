#!/usr/bin/python
""" """
import logging
from os import environ as env
import time
import boto3
from datetime import datetime
import re
from botocore.exceptions import ClientError
from s3_utils import (
    save_csv_file_versions_to_files,
    save_csv_file_to_s3,
    delete_all_versions_of_csv,
)
from csv_merger import (
    merge_csv_files_from_directory,
)
from validate_merge import validate_merge


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)


SQS_URL = env.get(
    "SQS_URL", "https://sqs.us-east-1.amazonaws.com/477591219415/dev-cidb2-sqs-queue"
)
REGION = env.get("LAMBDA_REGION", "us-east-1")
INITIAL_DELAY = int(env.get("INITIAL_DELAY", 1))
MAX_RETRIES = int(env.get("MAX_RETRIES", 3))
BUCKET_NAME = env.get("BUCKET_NAME", "evsharesvcnonprod-us-east-1-priv-cidb-ev-logs")
TIME_FRAME = int(env.get("TIME_FRAME", 0))  # Timeframe in minutes
LAMBDA_REBALANCE = env.get("LAMBDA_REBALANCE", "get-rebalance-metadata")
service_name = "AWS::IAM::Policy"
today = datetime.today()
year = today.strftime("%Y")
month = today.strftime("%B").lower()
day = today.strftime("%d")
timestamp = today.strftime("%Y%d%m")
BASE_DIR = "Custom"


# ---------------------------------------------------------
def get_service_object_key(service_name, time_window=0, base_dir=BASE_DIR):
    """
    Generate a service-specific object key for S3 storage.

    Args:
        service_name (str): The AWS service name to include in the filename

    Returns:
        str: The full object key to use for S3 storage
    """
    # Replace colons with hyphens to create valid filenames
    safe_service_name = re.sub(r":+", "-", service_name)
    # Include service name as prefix in the CSV filename
    # update naming convention
    service_csv_file = (
        f"{base_dir}/{safe_service_name}/{safe_service_name}-{year}-{month}-{day}"
    )
    if time_window:
        modified_timestamp = time_frame(time_window).strftime("%Y%d%m-%H-%M")
        # update naming convention
        service_csv_file = f"{base_dir}/{safe_service_name}/{safe_service_name}-{year}-{month}-{day}-{modified_timestamp}"

    return service_csv_file


def time_frame(timeframe):
    windows_minutes = timeframe
    now = datetime.today()
    rounded_minutes = (now.minute // windows_minutes) * windows_minutes
    adjusted_time = now.replace(minute=rounded_minutes, second=0)
    return adjusted_time


# ---------------------------------------------------------


def retry(max_retries=3, initial_delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.info("[Attempt %s] failed with error: %s", attempt, e)
                    if attempt == max_retries:
                        logger.error("Max retries reached!")
                        raise
                    time.sleep(delay)
                logger.info("Retrying in %s seconds...", delay)
                logger.info("Attempt %s of %s", attempt, max_retries)

        return wrapper

    return decorator


# @retry(max_retries=MAX_RETRIES, initial_delay=INITIAL_DELAY)
def validate_sqs_empty(sqs_url: str) -> bool:
    sqs = boto3.client("sqs", region_name=REGION)
    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=sqs_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateNumberOfMessagesDelayed",
            ],
        )["Attributes"]
        num_messages = int(attrs.get("ApproximateNumberOfMessages", 0))
        num_not_visible = int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
        num_delayed = int(attrs.get("ApproximateNumberOfMessagesDelayed", 0))
        logging.info(
            f"SQS Queue Stats - Available: {num_messages}, NotVisible: {num_not_visible}, Delayed: {num_delayed}"
        )
        return (num_messages + num_not_visible + num_delayed) == 0
    except Exception as e:
        logging.error(f"Error checking SQS queue: {e}")
        return False


def wait_for_empty_queue(
    sqs_url, max_attempts=5, initial_backoff=60, backoff_multiplier=1
):
    """
    Wait for the SQS queue to become empty, using exponential backoff.

    Args:
        sqs_url (str): URL of the SQS queue to check
        max_attempts (int): Maximum number of attempts to check if queue is empty
        initial_backoff (int): Initial backoff time in seconds
        backoff_multiplier (float): Multiplier for exponential backoff

    Returns:
        bool: True if queue becomes empty, False if max attempts reached and queue still not empty
    """
    for attempt in range(1, max_attempts + 1):
        logger.info(
            f"Checking if SQS queue is empty (attempt {attempt}/{max_attempts})"
        )

        if validate_sqs_empty(sqs_url):
            logger.info(f"SQS queue is empty after {attempt} attempts")
            # TODO: Review. Dismiss first attempt if successfully
            if attempt == 1:
                logger.info("First Attempt discarded")
                continue
            else:
                return True

        if attempt < max_attempts:
            wait_time = initial_backoff * (backoff_multiplier ** (attempt - 1))
            logger.info(
                f"SQS queue not empty. Waiting {wait_time} seconds before retry..."
            )
            time.sleep(wait_time)
        else:
            logger.warning(f"SQS queue still not empty after {max_attempts} attempts.")
            return False

    return False  # This should not be reached but added for safety


def write_csv_buffer_to_s3(config_client, csv_buffer, bucket_name, object_key):
    """
    Write CSV buffer to S3
    """
    try:
        # Create CSV in memory

        if csv_buffer:
            # Upload to S3
            config_client.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=csv_buffer,
                ContentType="text/csv",
            )

            logger.info(
                f"Wrote {len(csv_buffer)} rows to s3://{bucket_name}/{object_key}"
            )
            return {
                "status": "success",
                "bucket": bucket_name,
                "key": object_key,
                "count": len(csv_buffer),
            }
        else:
            logger.warning("No rows to write")
            return {"status": "warning", "message": "No rows to write"}
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        logger.error(f"S3 error: {error_code} - {error_message}")


def lambda_handler(event, context):
    try:
        # Clean up   lambda rebalance output files
        s3 = boto3.client("s3", region_name="us-east-1")
        rebalance_dir = f"Custom/{LAMBDA_REBALANCE}/input.json"
        logger.info(f"Deleting S3 object: s3://{BUCKET_NAME}/{rebalance_dir}")
        s3.delete_object(Bucket=BUCKET_NAME, Key=rebalance_dir)
        # Merge and delete service name versions
        # --------------------------------------------------------------------------
        # CWA, EVR, EC2
        # ---------------------------------------------------------------------------
        service_type_list = [
            "AWS::CloudWatch::Alarm",
            "AWS::AppConfig::DeploymentStrategy",
            "AWS::Events::Rule",
            "AWS::Route53::HostedZone",
            "AWS::EC2::Fleet",
            "AWS::Cassandra::Keyspace",
        ]
        for service_type in service_type_list:
            object_key = get_service_object_key(service_type, TIME_FRAME)
            OBJECT_KEY = f"{object_key}"
            temp_directory = "/tmp"
            status_versions = save_csv_file_versions_to_files(
                BUCKET_NAME,
                object_key=f"{OBJECT_KEY}-versions",
                output_dir=f"{temp_directory}/{object_key}",
                region="us-east-1",
            )
            if not status_versions:
                logger.error("Failed to save file S3 Versions")
                return
            status_merge = merge_csv_files_from_directory(
                directory_path=f"{temp_directory}/{object_key}",
                output_filename=f"{temp_directory}/{object_key}/merged.csv",
            )
            if not status_merge:
                logger.error("Failed to merge files")
                return
            is_valid, missing_arns, _, _ = validate_merge(
                merged_file=f"{temp_directory}/{object_key}/merged.csv",
                source_directory=f"{temp_directory}/{object_key}",
            )
            if not is_valid:
                logger.error(
                    f"Found {len(missing_arns)} ARNs missing from merged file:"
                )
                OBJECT_KEY_MERGED = f"{object_key}-error.csv"
            else:
                OBJECT_KEY_MERGED = f"{object_key}.csv"
            status_save = save_csv_file_to_s3(
                bucket_name=BUCKET_NAME,
                object_key=OBJECT_KEY_MERGED,
                file_name=f"{temp_directory}/{object_key}/merged.csv",
                region="us-east-1",
            )
            if not status_save:
                logger.error("Failed to save merged file to S3")
                return
            else:
                if delete_all_versions_of_csv(
                    BUCKET_NAME, key=f"{OBJECT_KEY}-versions", region="us-east-1"
                ):
                    logger.info(f"{OBJECT_KEY}-versions deleted successfully")
            logger.info("CSV files processed and merged successfully.")
        # --------------------------------------------------------------------------
        # Process IAM Policies file versions from S3
        # --------------------------------------------------------------------------
        # Use the new function with parameters from environment variables or defaults
        max_attempts = int(env.get("MAX_QUEUE_CHECK_ATTEMPTS", 5))
        initial_backoff = int(env.get("INITIAL_BACKOFF_SECONDS", 60))
        backoff_multiplier = float(env.get("BACKOFF_MULTIPLIER", 2.0))
        object_key = get_service_object_key(service_name, TIME_FRAME)

        # Global default for backward compatibility
        OBJECT_KEY = f"{object_key}"
        temp_directory = "/tmp"
        if wait_for_empty_queue(
            SQS_URL, max_attempts, initial_backoff, backoff_multiplier
        ):
            logger.info("SQS queue is empty. Proceeding with S3 operations.")

            status_versions = save_csv_file_versions_to_files(
                BUCKET_NAME,
                object_key=f"{OBJECT_KEY}-versions",
                output_dir=f"{temp_directory}/{object_key}",
                region="us-east-1",
            )
            if not status_versions:
                logger.error("Failed to save file S3 Versions")
                return

            status_merge = merge_csv_files_from_directory(
                directory_path=f"{temp_directory}/{object_key}",
                output_filename=f"{temp_directory}/{object_key}/merged.csv",
            )
            if not status_merge:
                logger.error("Failed to merge files")
                return

            is_valid, missing_arns, _, _ = validate_merge(
                merged_file=f"{temp_directory}/{object_key}/merged.csv",
                source_directory=f"{temp_directory}/{object_key}",
            )
            if not is_valid:
                logger.error(
                    f"Found {len(missing_arns)} ARNs missing from merged file:"
                )
                OBJECT_KEY_MERGED = f"{object_key}-error.csv"
            else:
                OBJECT_KEY_MERGED = f"{object_key}.csv"

            status_save = save_csv_file_to_s3(
                bucket_name=BUCKET_NAME,
                object_key=OBJECT_KEY_MERGED,
                file_name=f"{temp_directory}/{object_key}/merged.csv",
                region="us-east-1",
            )
            if not status_save:
                logger.error("Failed to save merged file to S3")
                return
            else:
                if delete_all_versions_of_csv(
                    BUCKET_NAME, key=f"{OBJECT_KEY}-versions", region="us-east-1"
                ):
                    logger.info(f"{OBJECT_KEY}-versions deleted successfully")

            logger.info("CSV files processed and merged successfully.")
            return {"statusCode": 200, "body": "Merge operation completed successfully"}

        else:
            logger.warning(
                "Merge operation postponed as SQS queue is not empty after maximum retries."
            )
            return {
                "statusCode": 202,
                "body": "SQS queue not empty after maximum retries. Merge operation postponed.",
            }

    except Exception as e:
        logging.error(f"Error in lambda_handler: {str(e)}")
        raise e


if __name__ == "__main__":
    lambda_handler(None, None)
