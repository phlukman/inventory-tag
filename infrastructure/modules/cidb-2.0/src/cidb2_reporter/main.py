#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retrieve SQS queue messages

A script for lambda to retrieve messages from SQS queue for a list of AWS services tags and generate a csv report.
With S3 versioning to handle concurrency instead of locking.
"""
import json
import logging
from os import environ as env
import boto3
from datetime import datetime
import csv
import re
import io
import uuid
import time
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --------------------------------------------------------
# Environment Variables and Configuration
# --------------------------------------------------------
# Lambda-provided environment variables
EXECUTION_ENV = env.get("AWS_EXECUTION_ENV")
TIME_FRAME = int(env.get("TIME_FRAME", 0))  # Timeframe in minutes
service_name = "AWS::IAM::Policy"


# --------------------------------------------------------
# Helper Functions for Data Handling
# --------------------------------------------------------
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# --------------------------------------------------------
# Construct file path
# --------------------------------------------------------
today = datetime.today()
year = today.strftime("%Y")
month = today.strftime("%B").lower()
day = today.strftime("%d")
timestamp = today.strftime("%Y%d%m")
BASE_DIR = "Custom"


def get_service_object_key(service_name, time_window=0, base_dir=BASE_DIR):
    """
    Generate a service-specific object key for S3 storage.

    Args:
        service_name (str): The AWS service name to include in the filename

    Returns:
        str: The full object key to use for S3 storage
    """
    # Replace colons with hyphens to create valid filenames
    # safe_service_name = service_name.replace(':', '-')
    safe_service_name = re.sub(r":+", "-", service_name)
    service_csv_file = f"{base_dir}/{safe_service_name}/{safe_service_name}-{year}-{month}-{day}-versions"
    if time_window:
        modified_timestamp = time_frame(time_window).strftime("%Y%d%m-%H-%M")
        service_csv_file = f"{base_dir}/{safe_service_name}/{safe_service_name}-{year}-{month}-{day}-{modified_timestamp}-versions"

    return service_csv_file


def time_frame(timeframe):
    windows_minutes = timeframe

    now = datetime.today()
    rounded_minutes = (now.minute // windows_minutes) * windows_minutes
    adjusted_time = now.replace(minute=rounded_minutes, second=0)
    return adjusted_time


if EXECUTION_ENV:
    BUCKET_NAME = env.get("BUCKET_NAME")
    TO_FILE = False
    REGION = env.get("AWS_REGION")
else:
    REGION = "us-east-1"
    QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/477591219415/dev-cidb2-sqs-queue"
    TO_FILE = True
    BUCKET_NAME = "evsharesvcnonprod-us-east-1-priv-cidb-ev-logs"


def read_messages_from_event(response):
    """
    Process incoming SQS messages from Lambda event

    Args:
        response: Lambda event containing SQS messages

    Returns:
        dict: Messages organized by service name
    """
    service_messages = {}
    try:
        # Log batch information
        batch_size = len(response.get("Records", []))
        logger.info(f"Processing batch of {batch_size} SQS messages")

        for message in response.get("Records", []):
            try:
                # Parse the SQS message body
                body = json.loads(message["body"])
                aws_service = (
                    body.get("MessageAttributes", {})
                    .get("Service", {})
                    .get("Value", "unknown")
                )

                # Initialize list for this service if it doesn't exist
                if aws_service not in service_messages:
                    service_messages[aws_service] = []

                # Check if the body contains an SNS message
                if "Message" in body:
                    sns_message = json.loads(body["Message"])
                    service_messages[aws_service].append(sns_message)

                    # Log successful message processing
                    logger.debug(
                        f"Successfully processed message for service: {aws_service}"
                    )
            except Exception as e:
                logger.error(
                    f"Error processing individual message: {str(e)}", exc_info=True
                )
    except Exception as e:
        logger.error(f"Error processing batch of messages: {str(e)}", exc_info=True)

    # Log processing summary
    service_count = len(service_messages)
    total_messages = sum(len(messages) for messages in service_messages.values())
    logger.info(f"Processed {total_messages} messages across {service_count} services")

    return service_messages


# -----------------------------------------------------------------------------------------


def messages_to_csv(messages, awsconfig_service_name, to_file=False):
    """
    Create a CSV file with fields: Type, Arn, Tags, and AWSConfig.

    Args:
        messages (list): List of processed messages containing policy data.
        awsconfig_service_name (str): AWS service name for the messages.
        to_file (bool): Whether to write to a file in addition to returning rows.

    Returns:
        list: List of dictionaries representing CSV rows.
    """
    arn_regex = r"^arn:aws:(?P<service>[^:]+):(?P<region>[^:]*):(?P<account_id>[^:]*):(?P<resource_name>[^:]+)\/(?P<resource>.+)$"
    csv_rows = []
    processed_count = 0
    error_count = 0

    # Log start of batch processing
    logger.info(
        f"Starting to process batch of {len(messages)} messages for service {awsconfig_service_name}"
    )

    try:
        for message in messages:
            try:
                # Extract fields from the message
                policy_arn = (
                    message.get("message", {}).get("data", {}).get("PolicyArn", "N/A")
                )
                if policy_arn == "N/A":
                    logger.warning(f"Message missing PolicyArn: {message}")
                    continue

                policy_tags = message.get("message", {}).get("data", {}).get("Tags", {})

                # Handle potential regex errors with more robust error handling
                try:
                    match = re.match(arn_regex, policy_arn)
                    if not match:
                        logger.warning(
                            f"ARN does not match expected format: {policy_arn}"
                        )
                        continue
                    match_values = match.groupdict()
                except Exception as regex_error:
                    logger.error(f"Error parsing ARN {policy_arn}: {str(regex_error)}")
                    continue

                policy_name = awsconfig_service_name
                tags_json = json.dumps(policy_tags).replace('"', "'")
                csv_rows.append(
                    {
                        "Type": policy_name if policy_name else "N/A",
                        "AWSAccountId": match_values["account_id"],
                        "Arn": policy_arn if policy_arn else "N/A",
                        "Tags": tags_json or "{}",
                        #    "AWSConfig": aws_config_conf_decoded,
                    }
                )

                if not to_file:
                    processed_count += 1

            except Exception as msg_error:
                if not to_file:
                    error_count += 1
                logger.error(
                    f"Error processing message: {str(msg_error)}", exc_info=True
                )
                # Continue with next message

        # Log summary of processing
        logger.info(
            f"Processed {processed_count} messages with {error_count} errors for service {awsconfig_service_name}"
        )
        return csv_rows

    except Exception as e:
        logger.error(f"CSV processing error: {str(e)}", exc_info=True)
        raise


def write_csv_to_s3(config_client, rows, bucket_name, object_key, request_id=None):
    """
    Write CSV rows to S3 using versioning instead of locking

    Args:
        config_client: Boto3 S3 client
        rows: List of dictionaries representing CSV rows
        bucket_name: S3 bucket name
        object_key: S3 object key
        request_id: Unique ID for the current request for tracing

    Returns:
        dict: Upload result including version_id
    """
    log_event(
        "info",
        "Writing rows to S3",
        request_id=request_id,
        bucket=bucket_name,
        object_key=object_key,
        row_count=len(rows),
    )

    try:
        # Create CSV in memory
        start_time = time.time()
        csv_buffer = io.StringIO(newline="")

        if rows:
            # Get fieldnames from the first row
            fieldnames = rows[0].keys()
            if fieldnames is None:
                fieldnames = ["Type", "Arn", "Tags", "AWSConfig"]
                log_event(
                    "warning",
                    "No fieldnames found in rows, using default",
                    request_id=request_id,
                    bucket=bucket_name,
                    object_key=object_key,
                    default_fieldnames=fieldnames,
                )

            # Write CSV
            writer = csv.DictWriter(
                csv_buffer, fieldnames=fieldnames, lineterminator="\r\n"
            )
            writer.writeheader()
            writer.writerows(rows)
            csv_prep_time = time.time() - start_time

            # Upload to S3 - S3 versioning will automatically create a new version
            upload_start_time = time.time()
            response = config_client.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=csv_buffer.getvalue(),
                ContentType="text/csv",
            )
            upload_time = time.time() - upload_start_time
            total_time = time.time() - start_time

            # Get the version ID from the response
            version_id = response.get("VersionId", "None")

            log_event(
                "info",
                "Successfully wrote rows to S3",
                request_id=request_id,
                bucket=bucket_name,
                object_key=object_key,
                row_count=len(rows),
                version_id=version_id,
                csv_prep_time_seconds=round(csv_prep_time, 3),
                upload_time_seconds=round(upload_time, 3),
                total_time_seconds=round(total_time, 3),
            )

            return {
                "status": "success",
                "bucket": bucket_name,
                "key": object_key,
                "version_id": version_id,
                "rows": len(rows),
            }
        else:
            # No rows to write
            log_event(
                "warning",
                "No rows to write to S3",
                request_id=request_id,
                bucket=bucket_name,
                object_key=object_key,
            )

            return {
                "status": "warning",
                "bucket": bucket_name,
                "key": object_key,
                "message": "No rows to write",
            }
    except Exception as e:
        log_event(
            "error",
            "Error writing to S3",
            request_id=request_id,
            bucket=bucket_name,
            object_key=object_key,
            error=str(e),
            traceback=traceback.format_exc(),
        )

        return {
            "status": "error",
            "message": str(e),
            "bucket": bucket_name,
            "key": object_key,
        }


def log_event(level, message, **kwargs):
    """
    Log an event with structured data

    Args:
        level: Log level (info, warning, error)
        message: Log message
        kwargs: Additional structured data to log
    """
    log_data = {"message": message}
    log_data.update(kwargs)

    if level.lower() == "info":
        logger.info(json.dumps(log_data))
    elif level.lower() == "warning":
        logger.warning(json.dumps(log_data))
    elif level.lower() == "error":
        logger.error(json.dumps(log_data))
    else:
        logger.info(json.dumps(log_data))


# --------------------------------------------------------
# Set S3 Client
# --------------------------------------------------------
def set_s3_client(session=None, region=None):
    """
    Set up an S3 client with the specified region and profile name

    Args:
        region (str, optional): AWS region. Defaults to None.
        profile_name (str, optional): AWS profile name. Defaults to None.

    Returns:
        boto3.client: S3 client
    """
    try:

        # session = boto3.Session(region_name=region)

        s3_client = session.client("s3", region_name=region)
        return s3_client
    except Exception as e:
        logger.error(f"S3 error: {str(e)}")
        return {
            "status": "error",
            "error_code": e.response["Error"]["Code"],
            "message": e.response["Error"]["Message"],
        }


# --------------------------------------------------------
# Lambda Handler
# --------------------------------------------------------
def lambda_handler(event, context):
    # Generate a unique request ID for tracing through logs
    request_id = str(uuid.uuid4())
    execution_start_time = time.time()

    log_event(
        "info",
        "Starting Lambda execution",
        request_id=request_id,
        execution_env=EXECUTION_ENV if EXECUTION_ENV else "local",
        lambda_function="cidb2_reporter",
    )

    # messages = {}
    raw_messages = {}
    # current_messages = {}
    metrics = {
        "status": "success",
        "message_count": 0,
        "csv_row_count": 0,
        "failed_messages": 0,
        "successful_messages": 0,
    }

    try:
        client_session = boto3.Session()
        s3 = set_s3_client(client_session, region="us-east-1")

        # Processing stage timing
        stage_timings = {}

        # Process messages stage
        stage_start = time.time()
        if EXECUTION_ENV:
            log_event(
                "info", "Reading messages from Lambda Event", request_id=request_id
            )

            # Track failed message identifiers
            failed_message_ids = []

            # Process the SQS batch
            try:
                raw_messages = read_messages_from_event(event)
            except Exception as e:
                log_event(
                    "error",
                    "Failed to read messages from event",
                    request_id=request_id,
                    error=str(e),
                    traceback=traceback.format_exc(),
                )
                # Re-raise to return all messages to queue
                raise

            # Read existing CSV from S3
            s3_read_start = time.time()

            stage_timings["s3_read_time"] = round(
                (time.time() - s3_read_start) * 1000, 2
            )

        # Log message count metrics
        total_message_count = sum(len(messages) for messages in raw_messages.values())
        metrics["message_count"] = total_message_count
        log_event(
            "info",
            "Received messages",
            request_id=request_id,
            message_count=metrics["message_count"],
        )

        if metrics["message_count"] == 0:
            log_event("info", "No messages to process", request_id=request_id)
            metrics["status"] = "no_messages"
            metrics["total_time_ms"] = round(
                (time.time() - execution_start_time) * 1000, 2
            )

            return {
                "status": "warning",
                "message": "No messages to process",
                "request_id": request_id,
                "metrics": metrics,
            }

        # Track all processed CSV rows
        all_csv_rows = []

        # Track rows by service for separate file writing
        service_csv_data = {}

        # Process messages into CSV rows
        csv_processing_start = time.time()

        # Process each service's messages separately
        for service_name, service_messages in raw_messages.items():
            # Track count of messages by service
            messages_count = len(service_messages)

            log_event(
                "info",
                "Processing messages for service",
                request_id=request_id,
                service=service_name,
                message_count=messages_count,
            )

            # Convert this service's messages to CSV rows
            if messages_count > 0:
                try:
                    # Convert messages to CSV rows for this service
                    service_csv_rows = messages_to_csv(
                        service_messages, service_name, to_file=TO_FILE
                    )

                    # Store rows for this specific service
                    service_csv_data[service_name] = service_csv_rows

                    # Add rows to our collection for metrics
                    all_csv_rows.extend(service_csv_rows)

                    # Update success metrics
                    metrics["successful_messages"] += messages_count

                    log_event(
                        "info",
                        "Converted service messages to CSV rows",
                        request_id=request_id,
                        service=service_name,
                        message_count=messages_count,
                        csv_row_count=len(service_csv_rows),
                    )
                except Exception as e:
                    # Track failure for this service's messages
                    metrics["failed_messages"] += messages_count
                    failed_message_ids.append(service_name)

                    log_event(
                        "error",
                        "Failed to process service messages",
                        request_id=request_id,
                        service=service_name,
                        message_count=messages_count,
                        error=str(e),
                        traceback=traceback.format_exc(),
                    )

        # Update CSV row metrics with total from all services
        metrics["csv_row_count"] = len(all_csv_rows)
        stage_timings["csv_processing_time"] = round(
            (time.time() - csv_processing_start) * 1000, 2
        )

        log_event(
            "info",
            "Completed message batch processing",
            request_id=request_id,
            total_message_count=metrics["message_count"],
            total_csv_row_count=metrics["csv_row_count"],
        )

        # Write to S3 if in Lambda environment
        s3_write_failures = []
        if EXECUTION_ENV:
            # Process each service separately
            for service_name, service_rows in service_csv_data.items():
                # Skip if no rows for this service
                if not service_rows or len(service_rows) == 0:
                    continue

                try:
                    # Generate service-specific object key
                    object_key = get_service_object_key(service_name, TIME_FRAME)
                    service_object_key = f"{object_key}"

                    log_event(
                        "info",
                        "Writing service CSV data to S3",
                        request_id=request_id,
                        service=service_name,
                        object_key=service_object_key,
                    )

                    # Write service rows to S3
                    s3_write_start = time.time()
                    write_result = write_csv_to_s3(
                        s3,
                        service_rows,
                        BUCKET_NAME,
                        service_object_key,
                        request_id=request_id,
                    )
                    service_write_time = round((time.time() - s3_write_start) * 1000, 2)

                    if write_result["status"] != "success":
                        s3_write_failures.append(service_name)
                        if service_name not in failed_message_ids:
                            failed_message_ids.append(service_name)

                    log_event(
                        "info",
                        "Service CSV write completed",
                        request_id=request_id,
                        service=service_name,
                        status=write_result["status"],
                        row_count=len(service_rows),
                        write_time_ms=service_write_time,
                    )
                except Exception as e:
                    s3_write_failures.append(service_name)
                    if service_name not in failed_message_ids:
                        failed_message_ids.append(service_name)

                    log_event(
                        "error",
                        "Failed to write service data to S3",
                        request_id=request_id,
                        service=service_name,
                        error=str(e),
                        traceback=traceback.format_exc(),
                    )

        # Calculate total execution time
        metrics["total_time_ms"] = round((time.time() - execution_start_time) * 1000, 2)
        metrics["processing_time_ms"] = stage_timings.get("messages_processing_time", 0)
        metrics["s3_read_time_ms"] = stage_timings.get("s3_read_time", 0)
        metrics["s3_write_time_ms"] = stage_timings.get("s3_write_time", 0)

        # Check if there were any failures
        if EXECUTION_ENV and failed_message_ids:
            metrics["status"] = "error"
            error_message = f"Failed to process {len(failed_message_ids)} services out of {len(raw_messages)}"

            log_event(
                "warning",
                "Some messages failed processing",
                request_id=request_id,
                failed_services=failed_message_ids,
                failed_count=len(failed_message_ids),
                metrics=metrics,
            )

            # Raise exception to signal Lambda that processing failed
            # This will cause SQS to keep the messages in the queue for retry
            raise Exception(error_message)

        # Log final execution metrics
        log_event(
            "info",
            "Lambda execution completed successfully",
            request_id=request_id,
            metrics=metrics,
            stage_timings=stage_timings,
        )

        return {
            "status": "success",
            "message": f"Processed {metrics['successful_messages']} messages successfully into {metrics['csv_row_count']} CSV records",
            "request_id": request_id,
            "metrics": metrics,
        }
    except Exception as e:
        execution_time = round((time.time() - execution_start_time) * 1000, 2)
        metrics["total_time_ms"] = execution_time
        metrics["status"] = "error"

        log_event(
            "error",
            "Error in Lambda execution - Messages will be returned to queue",
            request_id=request_id,
            error=str(e),
            traceback=traceback.format_exc(),
            metrics=metrics,
        )

        # Re-raise the exception to signal to Lambda that processing failed
        # This will cause SQS to keep the messages in the queue for retry
        raise
