import boto3
import logging
import csv
import io
import os
import time
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def create_s3_client(region=None, profile_name=None):
    """
    Create S3 client

    Args:
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name

    Returns:
        boto3.client: S3 client
    """
    try:
        # Create session
        session = boto3.Session(region_name=region, profile_name=profile_name)

        # Create S3 client
        s3 = session.client("s3")

        return s3

    except Exception as e:
        logger.error(f"S3 error: {str(e)}")
        return None


def list_s3_file_versions(bucket_name, object_key, region=None, profile_name=None):
    """
    List all versions of an object in S3 bucket

    Args:
        bucket_name (str): S3 bucket name
        object_key (str): S3 object key
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name

    Returns:
        list: List of versions
    """
    try:
        # Create S3 client
        s3 = create_s3_client(region, profile_name)

        # List object versions
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = s3.list_object_versions(
                    Bucket=bucket_name, Prefix=object_key
                )
                break
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                else:
                    return []

        # Extract versions
        versions = response.get("Versions", [])

        # logger.info(f"Found {len(versions)} versions of s3://{bucket_name}/{object_key}")
        logger.info(f"Found {len(versions)} versions")
        return versions

    except Exception as e:
        logger.error(f"S3 error: {str(e)}")
        return []


def get_s3_file_content_by_version_id(
    bucket_name, object_key, version_id, region=None, profile_name=None
):
    """
    Get S3 file content by version ID

    Args:
        bucket_name (str): S3 bucket name
        object_key (str): S3 object key
        version_id (str): S3 object version ID
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name

    Returns:
        str: S3 file content
    """
    try:
        # Create S3 client
        s3 = create_s3_client(region, profile_name)

        # Get object
        response = s3.get_object(
            Bucket=bucket_name, Key=object_key, VersionId=version_id
        )

        # Read content
        content = response["Body"].read().decode("utf-8")

        logger.info(
            f"Read {len(content)} bytes from s3://{bucket_name}/{object_key} version {version_id}"
        )
        return content

    except Exception as e:
        logger.error(f"S3 error: {str(e)}")
        return None


def merge_csv_files(csv_contents):
    """
    Merge CSV files

    Args:
        csv_contents (list): List of CSV contents

    Returns:
        str: Merged CSV content
    """
    try:
        # Merge CSV contents
        merged_content = ""
        for content in csv_contents:
            merged_content += content
            merged_content += "\r"

        logger.info(f"Merged {len(csv_contents)} CSV files")
        return merged_content

    except Exception as e:
        logger.error(f"Error merging CSV files: {str(e)}")
        return None


def get_csv_dialect(content):
    """
    Get CSV dialect from content

    Args:
        content (str): CSV content
    Returns:
        str: CSV dialect
    """
    try:
        # Read CSV content
        csv_reader = csv.reader(io.StringIO(content))
        sample_row = next(csv_reader)

        # Detect dialect
        dialect = csv.Sniffer().sniff(content, delimiters=[",", ";", "\t"])

        logger.info(f"Detected CSV dialect: {dialect}")
        logger.info(f"Line terminator:{repr(dialect.lineterminator)}")
        return dialect

    except Exception as e:
        logger.error(f"Error detecting CSV dialect: {str(e)}")
        return None

    except Exception as e:
        logger.error(f"Error detecting CSV dialect: {str(e)}")
        return None


def save_csv_file_to_s3(bucket_name, object_key, file_name, region=None):
    """
    Save a local CSV file to S3.

    Args:
        s3_client: (deprecated) S3 client, not used. Use create_s3_client instead.
        bucket_name (str): S3 bucket name
        object_key (str): S3 object key
        file_name (str): Local file path to upload
        region (str, optional): AWS region

    Returns:
        bool: True if upload succeeded, False otherwise
    """
    try:
        s3 = create_s3_client(region)
        with open(file_name, "rb") as f:
            s3.upload_fileobj(f, bucket_name, object_key)
        logger.info(f"Uploaded {file_name} to s3://{bucket_name}/{object_key}")
        return True
    except Exception as e:
        logger.error(f"Error uploading file to S3: {str(e)}")
        return False


def save_csv_file_versions_to_files(
    bucket_name, object_key, output_dir, region=None, profile_name=None
):
    """
    Save all versions of a CSV file from S3 to separate local CSV files.
    Args:
        bucket_name (str): S3 bucket name
        object_key (str): S3 object key
        output_dir (str): Directory to save output CSV files
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name
    Returns:
        int: Number of files saved
    """
    try:
        versions = list_s3_file_versions(bucket_name, object_key, region, profile_name)
        if not versions:
            logger.error("No versions found.")
            return 0
        os.makedirs(output_dir, exist_ok=True)
        count = 0
        for version in versions:
            version_id = version["VersionId"]
            content = get_s3_file_content_by_version_id(
                bucket_name, object_key, version_id, region, profile_name
            )
            if content is not None:
                output_file = os.path.join(
                    output_dir,
                    f"{os.path.basename(object_key)}.version_{version_id}.csv",
                )
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"Saved version {version_id} to {output_file}")
                count += 1
        return count
    except Exception as e:
        logger.error(f"Error saving CSV versions to files: {str(e)}")
        return 0


def delete_all_versions_of_csv(bucket_name, key, region="us-east-1"):
    """
    Delete all versions of the specified CSV file from the given S3 bucket,
    with error handling and logging.

    :param bucket_name: Name of the S3 bucket
    :param key: S3 object key (e.g., 'path/to/myfile.csv')
    """
    s3 = create_s3_client(region)
    try:
        paginator = s3.get_paginator("list_object_versions")
        found = False
        for page in paginator.paginate(Bucket=bucket_name, Prefix=key):
            versions = page.get("Versions", [])
            delete_markers = page.get("DeleteMarkers", [])

            # Delete all file versions
            for version in versions:
                if version["Key"] == key:
                    found = True
                    try:
                        s3.delete_object(
                            Bucket=bucket_name, Key=key, VersionId=version["VersionId"]
                        )
                        logger.info(f"Deleted version: {version['VersionId']} of {key}")
                    except ClientError as e:
                        logger.info(
                            f"Failed to delete version {version['VersionId']}: {e}"
                        )

            # Delete all delete markers
            for marker in delete_markers:
                if marker["Key"] == key:
                    found = True
                    try:
                        s3.delete_object(
                            Bucket=bucket_name, Key=key, VersionId=marker["VersionId"]
                        )
                        logger.info(
                            f"Deleted delete marker: {marker['VersionId']} of {key}"
                        )
                    except ClientError as e:
                        logger.info(
                            f"Failed to delete delete marker {marker['VersionId']}: {e}"
                        )
        if not found:
            logger.info(f"No versions found for {key} in bucket {bucket_name}")
        return True
    except NoCredentialsError:
        logger.info("AWS credentials not found. Please configure your AWS credentials.")
    except EndpointConnectionError as e:
        logger.info(f"Could not connect to the endpoint: {e}")
    except ClientError as e:
        logger.info(f"An error occurred: {e}")
    except Exception as e:
        logger.info(f"Unexpected error: {e}")
