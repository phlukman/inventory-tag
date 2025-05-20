import boto3
import logging
import csv
import io
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
        s3 = session.client('s3')

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
        response = s3.list_object_versions(Bucket=bucket_name, Prefix=object_key)

        # Extract versions
        versions = response.get('Versions', [])

        #logger.info(f"Found {len(versions)} versions of s3://{bucket_name}/{object_key}")
        logger.info(f"Found {len(versions)} versions")
        return versions

    except Exception as e:
        logger.error(f"S3 error: {str(e)}")
        return []

def get_s3_file_content_by_version_id(bucket_name, object_key, version_id, region=None, profile_name=None):
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
        response = s3.get_object(Bucket=bucket_name, Key=object_key, VersionId=version_id)

        # Read content
        content = response['Body'].read().decode('utf-8')

        logger.info(f"Read {len(content)} bytes from s3://{bucket_name}/{object_key} version {version_id}")
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
        dialect = csv.Sniffer().sniff(content, delimiters=[',', ';', '\t'])

        logger.info(f"Detected CSV dialect: {dialect}")
        logger.info(f"Line terminator:{repr(dialect.lineterminator)}")
        return dialect

    except Exception as e:
        logger.error(f"Error detecting CSV dialect: {str(e)}")
        return None

    except Exception as e:
        logger.error(f"Error detecting CSV dialect: {str(e)}")
        return None

def merge_csv_files_from_s3(bucket_name, object_key, region=None, profile_name=None):
    """
    Merge CSV files from S3 bucket

    Args:
        bucket_name (str): S3 bucket name
        object_key (str): S3 object key
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name

    Returns:
        str: Merged CSV content
    """
    try:
        # Create S3 client
        s3 = create_s3_client(region, profile_name)

        # List object versions
        versions = list_s3_file_versions(bucket_name, object_key, region, profile_name)

        # Sort versions by LastModified in descending order
        sorted_versions = sorted(versions, key=lambda x: x['LastModified'], reverse=True)


        # Get content from each version
        contents = []
        for version in sorted_versions:
            version_id = version['VersionId']
            content = get_s3_file_content_by_version_id(bucket_name, object_key, version_id, region, profile_name)
            # TODO: Review
            lineterminator = get_csv_dialect(content).lineterminator 
            if len(contents) >= 1:
            
                #print(lines)
                filtered_row = lineterminator.join(content.splitlines()[1:])
                #filtered_row = content
                contents.append(filtered_row)

            else:
                logger.info(f"First chunk")
                #print(repr(content))
                logger.info(f"Len of chunk {len(content.splitlines())}")
                contents.append(content)

            # Merge contents
        logger.info(f"Merged {len(contents)} CSV files")
        
        merged_content = merge_csv_files(contents)

        logger.info(f"Merged {len(contents)} CSV files from s3://{bucket_name}/{object_key}")
        return merged_content

    except Exception as e:
        logger.error(f"S3 error: {str(e)}")
        return None
