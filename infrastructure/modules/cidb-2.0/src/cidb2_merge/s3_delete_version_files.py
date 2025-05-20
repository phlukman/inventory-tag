import sys
import os
import logging
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import re
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Constants

bucket_name = "evsharesvcnonprod-us-east-1-priv-cidb-ev-logs"

region = "us-east-1"

today = datetime.today()
year = today.strftime("%Y")
month = today.strftime("%B").lower()
day = today.strftime("%d")
timestamp = today.strftime("%Y%d%m")
service_name =  "AWS::IAM::Policy"
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


object_key=f"{get_service_object_key(service_name)}.csv"

def create_s3_client(region=None, profile_name=None):
    """
    Create an S3 client with optional region and profile name.
    """
    if profile_name:
        session = boto3.Session(profile_name=profile_name)
        return session.client('s3', region_name=region)
    else:
        return boto3.client('s3', region_name=region)
def list_s3_file_versions(bucket_name, object_key, region=None, profile_name=None):
    """
    List all versions of an object in S3 bucket.
    """
    try:
        s3 = create_s3_client(region, profile_name)
        response = s3.list_object_versions(Bucket=bucket_name, Prefix=object_key)
        versions = response.get('Versions', [])
        logger.info(f"Found {len(versions)} versions of s3://{bucket_name}/{object_key}")
        return versions
    except ClientError as e:
        logger.error(f"Error listing S3 file versions: {str(e)}")
        return []
def delete_s3_file_versions(bucket_name, object_key, region):
    """
    Delete all versions of a specific object in S3 bucket.
    """


    try:
        s3 = create_s3_client(region)
        versions = list_s3_file_versions(bucket_name, object_key, region)

        for version in versions:
            version_id = version['VersionId']
            s3.delete_object(Bucket=bucket_name, Key=object_key, VersionId=version_id)
            logger.info(f"Deleted version {version_id} of s3://{bucket_name}/{object_key}")

    except ClientError as e:
        logger.error(f"Error deleting S3 file versions: {str(e)}")

if __name__ == "__main__":
    try:
        # Delete all versions of the specified object
        logger.info(f"Deleting all versions of s3://{bucket_name}/{object_key}")
        response =  input("Press Enter to continue or 'q' to cancel: ")
        if not bucket_name or not object_key:
            logger.error("Bucket name and object key must be provided.")
            sys.exit(1)
        elif response == 'q':
            logger.info("Exiting without deleting.")
            sys.exit(0)
        # Call the delete function
        delete_s3_file_versions(bucket_name=bucket_name, object_key=object_key, region=region)
    except Exception as e:
        logger.error(f"Error  deleting s3 file versions: {str(e)}")
        sys.exit(1)
