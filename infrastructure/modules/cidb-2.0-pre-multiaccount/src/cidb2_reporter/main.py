#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retrieve SQS queue messages 

A script for lambda to retrieve messages from SQS queue for a list of AWS services tags and generate a csv report.
With S3 locking mechanism to prevent data loss from concurrent writes.
"""
import json
import logging
from os import environ as env
import boto3
from datetime import datetime, timedelta
import csv
import re
import io
import sys
import uuid
import time
import random
import traceback
from s3_locking import log_event as s3_log_event, write_with_lock  # Rename imported function to avoid conflict

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#--------------------------------------------------------
# Environment Variables and Configuration
#--------------------------------------------------------
# Lambda-provided environment variables
EXECUTION_ENV = env.get('AWS_EXECUTION_ENV')

#--------------------------------------------------------
# Helper Functions for Data Handling
#--------------------------------------------------------
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)   

#--------------------------------------------------------
# Construct file path
#--------------------------------------------------------
today = datetime.today()
year = today.strftime("%Y")
month = today.strftime("%B").lower()
day = today.strftime("%d")
timestamp = today.strftime("%Y%d%m")

def get_service_object_key(service_name):
    """
    Generate a service-specific object key for S3 storage.
    
    Args:
        service_name (str): The AWS service name to include in the filename
        
    Returns:
        str: The full object key to use for S3 storage
    """
    # Replace colons with hyphens to create valid filenames
    safe_service_name = service_name.replace(':', '-')
    
    # Include service name as prefix in the CSV filename
    service_csv_file = f"cidb-2.0/{year}/{month}/{safe_service_name}-{month}-{day}-{timestamp}.csv"
    return f"cidb2_reporter/{service_csv_file}"

# Global default for backward compatibility
CSV_FILE = f"cidb-2.0/{year}/{month}/{month}-{day}-{timestamp}.csv"
OBJECT_KEY=f"cidb2_reporter/{CSV_FILE}"

if EXECUTION_ENV:
    BUCKET_NAME = env.get('BUCKET_NAME')
    TO_FILE = False
    REGION = env.get('AWS_REGION')
else:
    REGION = "us-east-1"
    QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/477591219415/dev-cidb2-sqs-queue"
    TO_FILE = True
    BUCKET_NAME = "evsharesvcnonprod-us-east-1-priv-cidb-ev-logs"

#--------------------------------------------------------
# Read Messages from SQS
#--------------------------------------------------------
def read_messages_from_sqs( queue_url):
    """
    Read messages from an SQS queue and process SNS topics encapsulated within them.

    Args:
        queue_url (str): The URL of the SQS queue.

    Returns:
        list: A list of processed SNS messages.
    """
    sqs_client = boto3.client('sqs', region_name=REGION)
    processed_messages = []
    service_messages = {}
    empty_queue=False
    while not empty_queue:
        try:
            # Receive messages from the SQS queue
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=2,  # Adjust as needed
                WaitTimeSeconds=20,      # Long polling
                MessageAttributeNames=['All']
            )

            logger.info("Response from SQS:%s",response)

            if 'Messages' in response:
                logger.info(f"Received {len(response['Messages'])} messages from SQS.")
                #CSV Headers
                
                for message in response['Messages']:
                    try:
                        #print(response['Messages'])
                        # Parse the SQS message body
                        body = json.loads(message['Body'])
                        aws_service = body.get('MessageAttributes', {}).get('Service', {}).get('Value', None)
                        #print(message_attributes)

                        # Check if the body contains an SNS message
                        if 'Message' in body:
                            sns_message = json.loads(body['Message'])
                            #logger.info(f"Processing SNS message: {sns_message}")
                            processed_messages.append(sns_message)
                            service_messages[aws_service]=processed_messages

                        # Delete the message from the queue after processing
                        sqs_client.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=message['ReceiptHandle']
                        )
                        logger.info(f"Deleted message from SQS: {message['MessageId']}")

                    except Exception as e:
                        logger.error(f"Error processing message: {str(e)}")
            else:
                logger.info("No messages received from SQS.")
                empty_queue = True

        except Exception as e:
            logger.error(f"Error reading messages from SQS: {str(e)}")

        #return processed_messages
        return service_messages

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
        batch_size = len(response.get('Records', []))
        logger.info(f"Processing batch of {batch_size} SQS messages")
        
        for message in response.get('Records', []):
            try:
                # Parse the SQS message body
                body = json.loads(message['body'])
                aws_service = body.get('MessageAttributes', {}).get('Service', {}).get('Value', 'unknown')
                
                # Initialize list for this service if it doesn't exist
                if aws_service not in service_messages:
                    service_messages[aws_service] = []
                
                # Check if the body contains an SNS message
                if 'Message' in body:
                    sns_message = json.loads(body['Message'])
                    service_messages[aws_service].append(sns_message)
                    
                    # Log successful message processing
                    logger.debug(f"Successfully processed message for service: {aws_service}")
            except Exception as e:
                logger.error(f"Error processing individual message: {str(e)}", exc_info=True)
    except Exception as e:
        logger.error(f"Error processing batch of messages: {str(e)}", exc_info=True)
        
    # Log processing summary
    service_count = len(service_messages)
    total_messages = sum(len(messages) for messages in service_messages.values())
    logger.info(f"Processed {total_messages} messages across {service_count} services")
    
    return service_messages

def get_awsconfig_resource_config_by_arn(account,resource_type, arn):
    try:
        #----------------------------------------------------
        # Assume Account role
        #----------------------------------------------------
        if not EXECUTION_ENV:
            logger.info("Chaining configuration")
            source_role_arn = f"arn:aws:iam::477591219415:role/CIDB2-Inventory-Role"
            source_sts_client = boto3.client('sts')
            source_account_a_role = source_sts_client.assume_role(
                RoleArn=source_role_arn,
                RoleSessionName="SourceInventoryRoleSession"
            )
            source_account_a_credentials = source_account_a_role['Credentials']
             
            target_session = boto3.Session(
                aws_access_key_id=source_account_a_credentials['AccessKeyId'],
                aws_secret_access_key=source_account_a_credentials['SecretAccessKey'],
                aws_session_token=source_account_a_credentials['SessionToken']
            )
            sts_client = target_session.client('sts')
            role_arn = f"arn:aws:iam::{account}:role/cidb-inventory-role"
            sts_client = boto3.client('sts')
            account_a_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="InventoryRoleSession"
            )
            account_a_credentials = account_a_role['Credentials']
        else:
            role_arn = f"arn:aws:iam::{account}:role/cidb-inventory-role"
            sts_client = boto3.client('sts')
            account_a_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="InventoryRoleSession"
            )

            # Step 2: Create a session with Account A role credentials
            account_a_credentials = account_a_role['Credentials']
        #----------------------------------------------------
        #session = boto3.Session()
        session = boto3.Session(
            aws_access_key_id=account_a_credentials['AccessKeyId'],
            aws_secret_access_key=account_a_credentials['SecretAccessKey'],
            aws_session_token=account_a_credentials['SessionToken']
        )
        client_conf = session.client("config", "us-east-1")

        query = f"Select resourceId WHERE resourceType = '{resource_type}' AND arn = '{str(arn)}'"
        ########print(query)
        result = client_conf.select_resource_config(
            Expression= query
        )
        #print("Result:",result)
        if len(result.get('Results', [])):
            resource_id = json.loads(result.get('Results', [])[0]).get("resourceId", {})
            awsconfig_response = client_conf.get_resource_config_history(
                resourceType = resource_type,
                resourceId = str(resource_id),
                limit = 1
            )
            #print(awsconfig_response)
            if awsconfig_response['configurationItems']:
                return awsconfig_response['configurationItems'][0]
            else:
                return None
        else:
            return None
    except Exception as e:
        logger.error("Failed to get AwsConfig ResourceId: %s", str(e))
    
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
    logger.info(f"Starting to process batch of {len(messages)} messages for service {awsconfig_service_name}")
    
    # Process each message and create CSV rows
    if to_file:
        try:
            with open('sqs_messages.csv', 'w', newline='') as csvfile:
                fieldnames = ['Type', 'Arn', 'Tags', 'AWSConfig']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for message in messages:
                    try:
                        # Extract fields from the message
                        policy_arn = message.get('data', {}).get('PolicyArn', 'N/A')
                        policy_tags = message.get('data', {}).get('Tags', {})
                        match_values = re.match(arn_regex, policy_arn).groupdict()
                        policy_name = awsconfig_service_name
                        logger.debug(f"Processing message for ARN: {policy_arn}")
                        
                        aws_config_conf = get_awsconfig_resource_config_by_arn(
                            match_values["account_id"],
                            resource_type=awsconfig_service_name, 
                            arn=policy_arn
                        )
                        
                        # Write row to CSV
                        row_data = {
                            'Type': policy_name,
                            'Arn': policy_arn,
                            'Tags': json.dumps(policy_tags),
                            'AWSConfig': json.dumps(aws_config_conf, cls=DateTimeEncoder) if aws_config_conf else 'N/A'
                        }
                        
                        writer.writerow(row_data)
                        csv_rows.append(row_data)
                        processed_count += 1
                    except Exception as msg_error:
                        error_count += 1
                        logger.error(f"Error processing message: {str(msg_error)}", exc_info=True)
                        # Continue processing other messages
                
            logger.info(f"CSV file 'sqs_messages.csv' created with {processed_count} rows")
        except Exception as file_error:
            logger.error(f"CSV file creation error: {str(file_error)}", exc_info=True)
    
    # Process messages for returning CSV rows (always done)
    try:
        for message in messages:
            try:
                # Extract fields from the message
                policy_arn = message.get('data', {}).get('PolicyArn', 'N/A')
                if policy_arn == 'N/A':
                    logger.warning(f"Message missing PolicyArn: {message}")
                    continue
                    
                policy_tags = message.get('data', {}).get('Tags', {})
                
                # Handle potential regex errors with more robust error handling
                try:
                    match = re.match(arn_regex, policy_arn)
                    if not match:
                        logger.warning(f"ARN does not match expected format: {policy_arn}")
                        continue
                    match_values = match.groupdict()
                except Exception as regex_error:
                    logger.error(f"Error parsing ARN {policy_arn}: {str(regex_error)}")
                    continue
                
                policy_name = awsconfig_service_name
                
                # Get AWS config with error handling
                try:
                    aws_config_conf = get_awsconfig_resource_config_by_arn(
                        match_values["account_id"], 
                        resource_type=awsconfig_service_name, 
                        arn=policy_arn
                    )
                except Exception as config_error:
                    logger.error(f"Error getting AWS config for {policy_arn}: {str(config_error)}")
                    aws_config_conf = None
                
                # Create CSV row
                csv_rows.append({
                    'Type': policy_name,
                    'Arn': policy_arn,
                    'Tags': json.dumps(policy_tags),
                    'AWSConfig': json.dumps(aws_config_conf, cls=DateTimeEncoder) if aws_config_conf else 'N/A'
                })
                
                # Only increment if not already counted in file processing
                if not to_file:
                    processed_count += 1
                    
            except Exception as msg_error:
                if not to_file:
                    error_count += 1
                logger.error(f"Error processing message: {str(msg_error)}", exc_info=True)
                # Continue with next message
                
        # Log summary of processing
        logger.info(f"Processed {processed_count} messages with {error_count} errors for service {awsconfig_service_name}")
        return csv_rows
        
    except Exception as e:
        logger.error(f"CSV processing error: {str(e)}", exc_info=True)
        raise

#--------------------------------------------------------------
# CSV To S3
#--------------------------------------------------------------
def read_csv_from_s3(config_client, bucket_name, object_key):
    """
    Read a CSV file from S3

    Args:
        bucket_name (str): S3 bucket name
        object_key (str): S3 object key
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name

    Returns:
        dict: Result of the operation success, warning, error
    """
    try:

        # Get object from S3
        response = config_client.get_object(Bucket=bucket_name, Key=object_key)
        logger.info(f"File exists: s3://{bucket_name}/{object_key}")

        # Read CSV content
        csv_content = response['Body'].read().decode('utf-8')

        # Parse CSV content
        csv_reader = csv.DictReader(csv_content.splitlines())

        # Convert to list of dictionaries
        rows = list(csv_reader)

        logger.info(f"Read {len(rows)} rows from s3://{bucket_name}/{object_key}")
        return {
            "status": "success",
            "bucket": bucket_name,
            "key": object_key,
            "rows": rows
        }
    
    except config_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
             logger.warning(f"File does not exists: s3://{bucket_name}/{object_key}")
             return {
                 "status": "warning",
                "bucket": bucket_name,
                "key": object_key,
                "rows": []
             }
        else:
            logger.error(f"S3 error: {str(e)}")
            return {
                "status": "error",
                "bucket": bucket_name,
                "key": object_key,
                "rows": []
            }

def write_csv_to_s3(config_client, rows, bucket_name, object_key, lock_id=None, request_id=None):
    """
    Write CSV rows to S3
    
    Args:
        config_client: Boto3 S3 client
        rows: List of dictionaries representing CSV rows
        bucket_name: S3 bucket name
        object_key: S3 object key
        lock_id: Optional lock ID for logging
        request_id: Unique ID for the current request for tracing
        
    Returns:
        dict: Upload result
    """
    lock_info = f" with lock ID {lock_id}" if lock_id else ""
    s3_log_event("info", "Writing rows to S3", 
              request_id=request_id,
              bucket=bucket_name, 
              object_key=object_key, 
              row_count=len(rows), 
              lock_id=lock_id if lock_id else None)
    
    try:
        # Create CSV in memory
        start_time = time.time()
        csv_buffer = io.StringIO()
   
        if rows:
            # Get fieldnames from the first row
            fieldnames = rows[0].keys()
            if fieldnames is None:
                fieldnames = ['Type', 'Arn', 'Tags', 'AWSConfig']
                s3_log_event("warning", "No fieldnames found in rows, using default", 
                          request_id=request_id,
                          bucket=bucket_name, 
                          object_key=object_key, 
                          default_fieldnames=fieldnames)
            
            # Write CSV
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            csv_prep_time = time.time() - start_time
            
            # Upload to S3
            upload_start_time = time.time()
            config_client.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=csv_buffer.getvalue(),
                ContentType='text/csv'
            )
            upload_time = time.time() - upload_start_time
            total_time = time.time() - start_time
            
            s3_log_event("info", "Successfully wrote rows to S3", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      object_key=object_key, 
                      row_count=len(rows), 
                      lock_id=lock_id if lock_id else None,
                      csv_prep_time_seconds=round(csv_prep_time, 3),
                      upload_time_seconds=round(upload_time, 3),
                      total_time_seconds=round(total_time, 3))
                      
            return {
                "status": "success",
                "bucket": bucket_name,
                "key": object_key,
                "rows": len(rows)
            }
        else:
            # No rows to write
            s3_log_event("warning", "No rows to write to S3", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      object_key=object_key, 
                      lock_id=lock_id if lock_id else None)
                      
            return {
                "status": "warning",
                "bucket": bucket_name,
                "key": object_key,
                "message": "No rows to write"
            }
    except Exception as e:
        s3_log_event("error", "Error writing to S3", 
                  request_id=request_id,
                  bucket=bucket_name, 
                  object_key=object_key, 
                  lock_id=lock_id if lock_id else None,
                  error=str(e),
                  traceback=traceback.format_exc())
                  
        return {
            "status": "error",
            "message": str(e),
            "bucket": bucket_name,
            "key": object_key
        }

def write_csv_to_s3_with_lock(config_client, rows, bucket_name, object_key, max_attempts=None, request_id=None):
    """
    Write CSV rows to S3 with locking mechanism
    
    Args:
        config_client: Boto3 S3 client
        rows: List of dictionaries representing CSV rows
        bucket_name: S3 bucket name
        object_key: S3 object key
        max_attempts: Maximum number of retry attempts for lock acquisition
        request_id: Unique ID for the current request for tracing
        
    Returns:
        dict: Upload result
    """
    # Define a writer function to pass to write_with_lock
    def writer_func(lock_id):
        return write_csv_to_s3(config_client, rows, bucket_name, object_key, lock_id, request_id)
    
    # Use the s3_locking module's write_with_lock function
    return write_with_lock(
        config_client, bucket_name, object_key, writer_func, max_attempts, request_id
    )

#--------------------------------------------------------
# Set S3 Client
#--------------------------------------------------------
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

        #session = boto3.Session(region_name=region)

        s3_client = session.client('s3', region_name=region) 
        return s3_client
    except Exception as e:
        logger.error(f"S3 error: {str(e)}")
        return {
            "status": "error",
            "error_code": e.response['Error']['Code'],
            "message": e.response['Error']['Message']
        }

#--------------------------------------------------------
# Lambda Handler
#--------------------------------------------------------
def lambda_handler(event, context):
    # Generate a unique request ID for tracing through logs
    request_id = str(uuid.uuid4())
    execution_start_time = time.time()
    
    s3_log_event("info", "Starting Lambda execution", 
               request_id=request_id,
               execution_env=EXECUTION_ENV if EXECUTION_ENV else "local",
               lambda_function="cidb2_reporter")
    
    messages = {}
    raw_messages = {}
    current_messages = {}
    metrics = {
        "status": "success",
        "message_count": 0,
        "csv_row_count": 0,
        "failed_messages": 0,
        "successful_messages": 0
    }
    
    try:
        client_session = boto3.Session()
        s3 = set_s3_client(client_session, region="us-east-1")
        
        # Processing stage timing
        stage_timings = {}
        
        # Process messages stage
        stage_start = time.time()
        if EXECUTION_ENV:
            s3_log_event("info", "Reading messages from Lambda Event", 
                       request_id=request_id)
            
            # Track failed message identifiers
            failed_message_ids = []
            
            # Process the SQS batch
            try:
                raw_messages = read_messages_from_event(event)
            except Exception as e:
                s3_log_event("error", "Failed to read messages from event", 
                          request_id=request_id,
                          error=str(e),
                          traceback=traceback.format_exc())
                # Re-raise to return all messages to queue
                raise
            
            # Read existing CSV from S3
            s3_read_start = time.time()
            current_messages = read_csv_from_s3(s3, BUCKET_NAME, OBJECT_KEY)
            stage_timings["s3_read_time"] = round((time.time() - s3_read_start) * 1000, 2)
        else:
            s3_log_event("info", "Reading messages directly from SQS", 
                       request_id=request_id,
                       queue_url=QUEUE_URL)
            raw_messages = read_messages_from_sqs(queue_url=QUEUE_URL)
        
        stage_timings["messages_processing_time"] = round((time.time() - stage_start) * 1000, 2)
        
        # Log message count metrics
        total_message_count = sum(len(messages) for messages in raw_messages.values())
        metrics["message_count"] = total_message_count
        s3_log_event("info", "Received messages", 
                   request_id=request_id,
                   message_count=metrics["message_count"])
        
        if metrics["message_count"] == 0:
            s3_log_event("info", "No messages to process", 
                       request_id=request_id)
            metrics["status"] = "no_messages"
            metrics["total_time_ms"] = round((time.time() - execution_start_time) * 1000, 2)
            
            return {
                "status": "warning",
                "message": "No messages to process",
                "request_id": request_id,
                "metrics": metrics
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
            
            s3_log_event("info", "Processing messages for service", 
                      request_id=request_id,
                      service=service_name,
                      message_count=messages_count)
            
            # Convert this service's messages to CSV rows
            if messages_count > 0:
                try:
                    # Convert messages to CSV rows for this service
                    service_csv_rows = messages_to_csv(service_messages, service_name, to_file=TO_FILE)
                    
                    # Store rows for this specific service
                    service_csv_data[service_name] = service_csv_rows
                    
                    # Add rows to our collection for metrics
                    all_csv_rows.extend(service_csv_rows)
                    
                    # Update success metrics
                    metrics["successful_messages"] += messages_count
                    
                    s3_log_event("info", "Converted service messages to CSV rows", 
                              request_id=request_id,
                              service=service_name,
                              message_count=messages_count,
                              csv_row_count=len(service_csv_rows))
                except Exception as e:
                    # Track failure for this service's messages
                    metrics["failed_messages"] += messages_count
                    failed_message_ids.append(service_name)
                    
                    s3_log_event("error", "Failed to process service messages", 
                              request_id=request_id,
                              service=service_name,
                              message_count=messages_count,
                              error=str(e),
                              traceback=traceback.format_exc())
        
        # Update CSV row metrics with total from all services
        metrics["csv_row_count"] = len(all_csv_rows)
        stage_timings["csv_processing_time"] = round((time.time() - csv_processing_start) * 1000, 2)
        
        s3_log_event("info", "Completed message batch processing", 
                  request_id=request_id,
                  total_message_count=metrics["message_count"],
                  total_csv_row_count=metrics["csv_row_count"])
        
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
                    service_object_key = get_service_object_key(service_name)
                    
                    s3_log_event("info", "Writing service CSV data to S3", 
                              request_id=request_id,
                              service=service_name,
                              object_key=service_object_key)
                    
                    # Read existing CSV data for this service
                    current_service_data = read_csv_from_s3(s3, BUCKET_NAME, service_object_key, request_id=request_id)
                    
                    if current_service_data["status"] == "success":
                        # Combine existing and new rows
                        existing_rows = len(current_service_data['rows'])
                        s3_log_event("info", "Appending new rows to existing service CSV data", 
                                  request_id=request_id,
                                  service=service_name,
                                  existing_row_count=existing_rows,
                                  new_row_count=len(service_rows))
                                  
                        service_rows.extend(current_service_data['rows'])
                    
                    # Write service rows to S3
                    s3_write_start = time.time()
                    write_result = write_csv_to_s3_with_lock(s3, service_rows, BUCKET_NAME, service_object_key, request_id=request_id)
                    service_write_time = round((time.time() - s3_write_start) * 1000, 2)
                    
                    if write_result["status"] != "success":
                        s3_write_failures.append(service_name)
                        if service_name not in failed_message_ids:
                            failed_message_ids.append(service_name)
                    
                    s3_log_event("info", "Service CSV write completed", 
                              request_id=request_id,
                              service=service_name,
                              status=write_result["status"],
                              row_count=len(service_rows),
                              write_time_ms=service_write_time)
                except Exception as e:
                    s3_write_failures.append(service_name)
                    if service_name not in failed_message_ids:
                        failed_message_ids.append(service_name)
                    
                    s3_log_event("error", "Failed to write service data to S3", 
                              request_id=request_id,
                              service=service_name,
                              error=str(e),
                              traceback=traceback.format_exc())
        
        # Calculate total execution time
        metrics["total_time_ms"] = round((time.time() - execution_start_time) * 1000, 2)
        metrics["processing_time_ms"] = stage_timings.get("messages_processing_time", 0)
        metrics["s3_read_time_ms"] = stage_timings.get("s3_read_time", 0)
        metrics["s3_write_time_ms"] = stage_timings.get("s3_write_time", 0)
        
        # Check if there were any failures
        if EXECUTION_ENV and failed_message_ids:
            metrics["status"] = "error"
            error_message = f"Failed to process {len(failed_message_ids)} services out of {len(raw_messages)}"
            
            s3_log_event("warning", "Some messages failed processing", 
                      request_id=request_id,
                      failed_services=failed_message_ids,
                      failed_count=len(failed_message_ids),
                      metrics=metrics)
            
            # Raise exception to signal Lambda that processing failed
            # This will cause SQS to keep the messages in the queue for retry
            raise Exception(error_message)
        
        # Log final execution metrics
        s3_log_event("info", "Lambda execution completed successfully", 
                  request_id=request_id,
                  metrics=metrics,
                  stage_timings=stage_timings)
                  
        return {
            "status": "success",
            "message": f"Processed {metrics['successful_messages']} messages successfully into {metrics['csv_row_count']} CSV records",
            "request_id": request_id,
            "metrics": metrics
        }
    except Exception as e:
        execution_time = round((time.time() - execution_start_time) * 1000, 2)
        metrics["total_time_ms"] = execution_time
        metrics["status"] = "error"
        
        s3_log_event("error", "Error in Lambda execution - Messages will be returned to queue", 
                  request_id=request_id,
                  error=str(e),
                  traceback=traceback.format_exc(),
                  metrics=metrics)
                  
        # Re-raise the exception to signal to Lambda that processing failed
        # This will cause SQS to keep the messages in the queue for retry
        raise

if __name__ == '__main__':
    # Direct SNS message format
    event= {'Records': [{'messageId': '82b923c2-ce1e-4afc-a5a6-62648b06ee2a', 'receiptHandle': 'AQEBYBb9igrIKAwhWHLv2lMS7zGvAp3W2zSR+d8h/EFAt04efLvxcZc/2blLeV/ScI5MCynKpqZWlbz1ImFoHHsb/JvoXY1uuA2uPlYehA5OMM5IR8/kPRGMvYFDIbNgp47T4nArsOfqGbnjoCazEG7Qvytj3pu9APf8PnDQxjVJVMoECRqACGzzOqtJz8a0TzwlP1EjXKKlpc+qwGoijOcV+KLEquf4V2uKUzOtAr6u2M8vdrRumRRumGeeq32eTRHPMI/eiQkITw92Q8ZYFdWHVijrYQcM2oHQPbNPQHNl7HTZRxCKh3sm4E6ugve97YGzSgCby/sb7N3Lrdd5Xh3Xyx3SL8D12GWHZsTeFf9a0r9ivF8/jCHoHFIAaaPmkLhu2yF6tuVRbl1rU3Vu13+sSg==', 'body': '{\n  "Type" : "Notification",\n  "MessageId" : "26dbc29f-5865-5603-a3ae-a2029168ad0b",\n  "TopicArn" : "arn:aws:sns:us-east-1:477591219415:dev-cidb2-lambda-collector-sns-topic",\n  "Message" : "{\\"message\\": {\\"id\\": 1, \\"data\\": {\\"AccountId\\": \\"053210025230\\", \\"PolicyArn\\": \\"arn:aws:iam::053210025230:policy/KinesisFirehoseSplunk2022051914163538720000001d\\", \\"PolicyName\\": \\"KinesisFirehoseSplunk2022051914163538720000001d\\", \\"Tags\\": {\\"SOXBackup\\": \\"NA\\", \\"fin_billing_model\\": \\"dedicated\\", \\"sec_approval\\": \\"cloudsecarch-36365916\\", \\"sec_data_sensitivity\\": \\"highly_restricted\\", \\"fin_billing_environment\\": \\"labs\\", \\"inv_eon_id\\": \\"309816\\", \\"AppName\\": \\"Landing Zone\\", \\"sec_tam_environment\\": \\"dev\\", \\"obs_owning_contact\\": \\"itawscoreservices@eatonvance.com\\", \\"AppId\\": \\"lanz01\\", \\"PointOfContact\\": \\"ITAWSCoreServices@eatonvance.com\\", \\"SourceBranch\\": \\"https://github.com/Eaton-Vance-Corp/landing-zone\\", \\"DataType\\": \\"Highly Restricted\\", \\"Environment\\": \\"dev\\", \\"fin_billing_eon_id\\": \\"309816\\"}}}}",\n  "Timestamp" : "2025-05-13T22:25:17.091Z",\n  "SignatureVersion" : "1",\n  "Signature" : "sxAWItlE3jJZDbsEuRuN6TOZvjwMoswETOvhiR3n8E+ne+SkELvxBriSwDj2bYH3ARB9ZABCTsGZT/F1FZtUSKNpQJB/jZbL4aVGNwGwM9GuIVAPWSbduXUQGJuToJkCtno5uOTPT72d4LwyJV6mZilKq+WXdwVnDdiBiTc+cPFP5LYzE7R/Bp3hRfsYnuuYi6PpZOMSbgxYDiplBl8woyi8bG0GDFhx1+8+PHjLSd/WKFGOwJ7du9szkel+VCzOs/tJWzPj8vmxyEJ+EQQ3HNk66NOWvgVAlL6XAQi7CSWoXjLbXLsrkbwDuJw2fshHjsIcjPobhxbmjvUUyZ2sNg==",\n  "SigningCertURL" : "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-9c6465fa7f48f5cacd23014631ec1136.pem",\n  "UnsubscribeURL" : "https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:us-east-1:477591219415:dev-cidb2-lambda-collector-sns-topic:37f47522-29f1-4bec-92ad-eb8f5dd312ed",\n  "MessageAttributes" : {\n    "Service" : {"Type":"String","Value":"AWS::IAM::Policy"},\n    "Region" : {"Type":"String","Value":"global"},\n    "Source" : {"Type":"String","Value":"cidb2:inventory"}\n  }\n}', 'attributes': {'ApproximateReceiveCount': '1', 'SentTimestamp': '1747175117164', 'SenderId': 'AIDAIT2UOQQY3AUEKVGXU', 'ApproximateFirstReceiveTimestamp': '1747175117176'}, 'messageAttributes': {}, 'md5OfBody': '1e09c7aca8543ac59a94773e2bc6f1e1', 'eventSource': 'aws:sqs', 'eventSourceARN': 'arn:aws:sqs:us-east-1:477591219415:dev-cidb2-sqs-queue', 'awsRegion': 'us-east-1'}]}

    lambda_handler(event, None)
