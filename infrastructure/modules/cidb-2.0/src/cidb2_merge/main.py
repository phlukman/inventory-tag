#!/usr/bin/python
"""

"""
import logging
from os import environ as env
import time
import boto3
from datetime import datetime
import re
from botocore.exceptions import ClientError
from s3_utils import create_s3_client, list_s3_file_versions, merge_csv_files_from_s3

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)


SQS_URL = env.get("SQS_URL", "https://sqs.us-east-1.amazonaws.com/477591219415/dev-cidb2-sqs-queue")
REGION = env.get("LAMBDA_REGION", "us-east-1")
INITIAL_DELAY = env.get("INITIAL_DELAY",1)
MAX_RETRIES = env.get("MAX_RETRIES", 3)
BUCKET_NAME = env.get("BUCKET_NAME", "evsharesvcnonprod-us-east-1-priv-cidb-ev-logs")

service_name = "AWS::IAM::Policy"
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
    #safe_service_name = service_name.replace(':', '-')
    safe_service_name = re.sub(r':+', '_',service_name)
    # Include service name as prefix in the CSV filename
    service_csv_file = f"cidb-2.0/{year}/{month}/{safe_service_name}-{month}-{day}-{timestamp}"
    return f"cidb2_reporter/{service_csv_file}"


object_key=f"{get_service_object_key(service_name)}"

# Global default for backward compatibility
OBJECT_KEY=f"{object_key}.csv"
OBJECT_KEY_MERGED=f"{object_key}-merged.csv"



def retry(max_retries = 3, initial_delay = 1):
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

@retry(max_retries=MAX_RETRIES, initial_delay=INITIAL_DELAY)
def validate_sqs_empty(sqs_url:  str) -> bool:
    sqs = boto3.client("sqs", region_name=REGION)
    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=sqs_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateNumberOfMessagesDelayed"
            ]
        )["Attributes"]
        num_messages = int(attrs.get("ApproximateNumberOfMessages", 0))
        num_not_visible = int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
        num_delayed = int(attrs.get("ApproximateNumberOfMessagesDelayed", 0))
        logging.info(f"SQS Queue Stats - Available: {num_messages}, NotVisible: {num_not_visible}, Delayed: {num_delayed}")
        return (num_messages + num_not_visible + num_delayed) == 0
    except Exception as e:
        logging.error(f"Error checking SQS queue: {e}")
        return False

def write_csv_buffer_to_s3(config_client,csv_buffer,bucket_name, object_key):
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
                ContentType='text/csv'
            )

            logger.info(f"Wrote {len(csv_buffer)} rows to s3://{bucket_name}/{object_key}")
            return {
                "status": "success",
                "bucket": bucket_name,
                "key": object_key,
                "count": len(csv_buffer)
            }
        else:
            logger.warning("No rows to write")
            return {
                "status": "warning",
                "message": "No rows to write"
            }
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"S3 error: {error_code} - {error_message}")

def lambda_handler(event, context):
    try:

        if  validate_sqs_empty(SQS_URL):
            logger.info("SQS queue is empty. Proceeding with S3 operations.")
    
            s3_client = create_s3_client(region="us-east-1")

            versions = list_s3_file_versions(BUCKET_NAME, object_key=OBJECT_KEY, region="us-east-1")
            #logger.info("Found %s versions of %s file to merge", versions, OBJECT_KEY)
            merged_csv_data = merge_csv_files_from_s3(BUCKET_NAME, OBJECT_KEY, region="us-east-1")
            write_csv_buffer_to_s3(s3_client, merged_csv_data, BUCKET_NAME, OBJECT_KEY_MERGED)
    except Exception as e:
        logging.error(e)
        raise e
if __name__ == "__main__":
    lambda_handler(None, None)