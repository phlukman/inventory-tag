# CIDB2 Reporter Changes for S3 Versioning

This document outlines the targeted changes required in the Lambda function code to leverage S3 versioning instead of the current locking mechanism.

## Current Issues with Locking Mechanism

1. Race conditions in the check-then-create pattern
2. No proper `release_lock` function implementation
3. Complex error handling and retry logic
4. No lock ownership verification or expiration handling

## Changes Required in Lambda Function

The following changes should be applied to the existing code:

### 1. Remove Locking Dependency

```python
# Remove these imports/functions
# from s3_locking import acquire_lock, release_lock, check_stale_lock, break_stale_lock
```

### 2. Update CSV Reading Function

```python
def read_csv_from_s3(config_client, bucket_name, object_key):
    """
    Read a CSV file from S3 with versioning awareness
    
    Args:
        config_client: Boto3 S3 client
        bucket_name: S3 bucket name
        object_key: S3 object key
        
    Returns:
        list: Rows from the CSV file or empty list if not found
    """
    try:
        # Get the latest version of the object (default behavior of get_object)
        response = config_client.get_object(Bucket=bucket_name, Key=object_key)
        logger.info(f"File exists: s3://{bucket_name}/{object_key}, Version: {response.get('VersionId')}")
        
        # Process the CSV content as before
        content = response['Body'].read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        rows = list(csv_reader)
        
        logger.info(f"Read {len(rows)} rows from s3://{bucket_name}/{object_key}")
        return rows
        
    except config_client.exceptions.NoSuchKey:
        # File doesn't exist - return empty list
        logger.warning(f"File does not exist: s3://{bucket_name}/{object_key}")
        return []
    
    except Exception as e:
        # Log other errors
        logger.error(f"Error reading CSV file s3://{bucket_name}/{object_key}: {e}")
        return []
```

### 3. Update CSV Writing Function

```python
def write_csv_to_s3(config_client, rows, bucket_name, object_key):
    """
    Write CSV data to S3 with versioning awareness
    
    Args:
        config_client: Boto3 S3 client
        rows: List of dictionaries representing CSV rows
        bucket_name: S3 bucket name
        object_key: S3 object key
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create a CSV in memory
        csv_buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(csv_buffer, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        else:
            # Write an empty CSV with default headers if no rows
            writer = csv.DictWriter(csv_buffer, fieldnames=["policy_id", "timestamp"])
            writer.writeheader()
        
        csv_data = csv_buffer.getvalue()
        
        # Upload to S3 - S3 versioning will automatically create a new version
        response = config_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=csv_data,
            ContentType='text/csv'
        )
        
        logger.info(f"Wrote {len(rows)} rows to s3://{bucket_name}/{object_key}, Version: {response.get('VersionId')}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing CSV to s3://{bucket_name}/{object_key}: {e}")
        return False
```

### 4. Update Lambda Handler Code

```python
def lambda_handler(event, context):
    # Initialize S3 client
    s3 = boto3.client('s3')
    
    # Process each record
    for record in event['Records']:
        try:
            # Extract message data
            message_body = json.loads(record['body'])
            
            # Read existing data - no locking needed
            current_rows = read_csv_from_s3(s3, BUCKET_NAME, OBJECT_KEY)
            
            # Process and append new data
            processed_row = process_message(message_body)
            current_rows.append(processed_row)
            
            # Write back to S3 - no locking needed
            write_csv_to_s3(s3, current_rows, BUCKET_NAME, OBJECT_KEY)
            
        except Exception as e:
            logger.error(f"Error processing record: {e}")
```

## Key Benefits of This Approach

1. **Simplified Code**: No complex locking logic required
2. **Automatic Versioning**: S3 maintains versions automatically
3. **No Race Conditions**: Writes are atomic per version
4. **Data Safety**: Previous versions are preserved in case of errors
5. **Cost Management**: Old versions expire after 7 days (as configured in Terraform)

## Implementation Notes

- This approach requires that versioning is enabled on the S3 bucket (via the Terraform code)
- Lifecycle policies handle the expiration of old versions to control costs
- No code changes are needed to handle reading the latest version (S3 default behavior)
