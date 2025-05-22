#!/usr/bin/python
"""
CSV File Merger

This script merges multiple CSV files while preserving their format and header structure.
It ensures idempotent operation by always producing the same output when run with the same
input files, regardless of how many times it's run.
"""
import os
import csv
import io
import logging
import glob
import hashlib
from datetime import datetime
from collections import OrderedDict

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def get_csv_dialect(content):
    """
    Get CSV dialect from content

    Args:
        content (str): CSV content
    Returns:
        csv.Dialect: CSV dialect
    """
    try:
        # Read CSV content
        csv_reader = csv.reader(io.StringIO(content))
        next(csv_reader)  # Read first row to ensure there's content

        # Detect dialect
        dialect = csv.Sniffer().sniff(content, delimiters=[',', ';', '\t'])
        
        logger.info(f"Detected CSV dialect with delimiter: '{dialect.delimiter}', "
                    f"line terminator: {repr(dialect.lineterminator)}")
        return dialect

    except Exception as e:
        logger.error(f"Error detecting CSV dialect: {str(e)}")
        # Default to Excel dialect if detection fails
        logger.info("Using default Excel dialect")
        return csv.excel

def get_file_hash(file_path):
    """
    Calculate a hash for a file to check if it has changed
    
    Args:
        file_path (str): Path to the file
        
    Returns:
        str: Hash of the file content
    """
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_source_files(directory_path, pattern="*.csv", exclude_pattern="merged"):
    """
    Get source files while excluding files matching exclude_pattern
    
    Args:
        directory_path (str): Directory containing CSV files
        pattern (str): Pattern to match files
        exclude_pattern (str): Pattern to exclude from filenames
        
    Returns:
        list: List of file paths sorted by modification time (oldest first)
    """
    # Find all CSV files matching the pattern
    all_files = glob.glob(os.path.join(directory_path, pattern))
    
    # Filter out files containing the exclude pattern
    source_files = [f for f in all_files if exclude_pattern not in os.path.basename(f).lower()]
    
    # Sort files by modification time (oldest first)
    # This is important for idempotent operation
    source_files.sort(key=os.path.getmtime)
    
    return source_files

def merge_csv_files_from_directory(directory_path, output_filename=None, pattern="*.csv", exclude_pattern="merged", force=False):
    """
    Merge CSV files from a directory in an idempotent manner
    
    This function ensures that running it multiple times with the same input files
    will always produce the same output, regardless of when it's run.

    Args:
        directory_path (str): Path to directory containing CSV files
        output_filename (str, optional): Name of output file. If None, uses timestamp.
        pattern (str, optional): Pattern to match files. Default is "*.csv".
        exclude_pattern (str, optional): Pattern to exclude from files. Default is "merged".
        force (bool, optional): Force regeneration even if source files are unchanged

    Returns:
        str: Path to the merged file
    """
    try:
        # Get source files sorted by modification time (oldest first for idempotency)
        csv_files = get_source_files(directory_path, pattern, exclude_pattern)
        
        logger.info(f"Found {len(csv_files)} CSV files to merge")
        for f in csv_files:
            logger.info(f"  - {os.path.basename(f)}")
        
        if not csv_files:
            logger.warning("No CSV files found in directory")
            return None
            
        # Create output filename if not provided
        if not output_filename:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            output_filename = os.path.join(directory_path, f"merged-{timestamp}.csv")
        else:
            # If only filename is provided without path, add the directory path
            if not os.path.dirname(output_filename):
                output_filename = os.path.join(directory_path, output_filename)
        
        # Check if output file already exists and compare its hash with source files
        if os.path.exists(output_filename) and not force:
            # Get hash of all source files
            source_files_hash = hashlib.md5()
            for file_path in csv_files:
                source_files_hash.update(get_file_hash(file_path).encode())
            
            # Store hash in a metadata file
            hash_file = f"{output_filename}.hash"
            if os.path.exists(hash_file):
                with open(hash_file, 'r') as f:
                    existing_hash = f.read().strip()
                    
                    # If hash matches, files haven't changed, no need to reprocess
                    if existing_hash == source_files_hash.hexdigest():
                        logger.info(f"Source files unchanged since last merge. Using existing file: {output_filename}")
                        return output_filename
        
        # Read all CSV files into memory
        all_data = []
        header = None
        
        for i, file_path in enumerate(csv_files):
            logger.info(f"Processing file {i+1}/{len(csv_files)}: {os.path.basename(file_path)}")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    
                    if not rows:
                        logger.warning(f"File {os.path.basename(file_path)} is empty")
                        continue
                    
                    if header is None:
                        # First file with content provides the header
                        header = rows[0]
                        all_data.append(rows)
                    else:
                        # For subsequent files, check if header matches
                        if rows[0] != header:
                            logger.warning(f"Header in {os.path.basename(file_path)} doesn't match reference header.")
                            logger.warning(f"Expected: {header}")
                            logger.warning(f"Found: {rows[0]}")
                        all_data.append(rows)
            
            except Exception as e:
                logger.error(f"Error processing file {os.path.basename(file_path)}: {str(e)}")
                # Continue with other files
        
        if not all_data:
            logger.error("No valid data found in any CSV file")
            return None
        
        # Merge data preserving order of files (oldest first)
        merged_rows = []
        
        # Add header from first file
        if header:
            merged_rows.append(header)
        
        # Use ordered dictionary to maintain the order of insertion while ensuring uniqueness by ARN
        unique_rows = OrderedDict()
        
        # Process all files in order
        for file_data in all_data:
            # Skip the header row (first row) of each file
            for row in file_data[1:]:
                if len(row) > 1:  # Ensure row has the ARN column
                    # Use ARN (second column) as the unique key
                    arn = row[1]
                    # Only add if this ARN hasn't been seen before
                    # Last occurrence of each ARN will be preserved
                    unique_rows[arn] = row
        
        # Add all unique rows to result
        merged_rows.extend(unique_rows.values())
        
        # Write merged data to output file
        with open(output_filename, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(merged_rows)
        
        # Store hash in metadata file for idempotency check
        source_files_hash = hashlib.md5()
        for file_path in csv_files:
            source_files_hash.update(get_file_hash(file_path).encode())
            
        with open(f"{output_filename}.hash", 'w') as f:
            f.write(source_files_hash.hexdigest())
        
        logger.info(f"Successfully merged {len(csv_files)} files with {len(unique_rows)} unique records to: {output_filename}")
        return output_filename
        
    except Exception as e:
        logger.error(f"Error merging CSV files: {str(e)}")
        return None

def merge_csv_files_from_s3_v1(bucket_name, prefix, output_key=None, exclude_pattern="merged", region=None, profile_name=None, force=False, local_output_dir=None):
    """
    Merge CSV files from S3 in an idempotent manner
    
    This function ensures that running it multiple times with the same input files
    will always produce the same output, regardless of when it's run.

    Args:
        bucket_name (str): S3 bucket name
        prefix (str): S3 prefix to search for CSV files
        output_key (str, optional): Output S3 key for merged file. If None, uses timestamp.
        exclude_pattern (str, optional): Pattern to exclude from file keys. Default is "merged".
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name
        force (bool, optional): Force regeneration even if source files haven't changed
        local_output_dir (str, optional): Local directory to save a copy of the merged file
        
    Returns:
        tuple: (s3_key, local_file_path) - S3 key of the merged file and path to local copy
    """
    try:
        import hashlib
        import json
        from datetime import datetime
        from collections import OrderedDict
        import os
        from s3_utils import create_s3_client
        logger.info(f"Merging CSV files from S3 bucket {bucket_name} with prefix {prefix}")
        
        # Create S3 client
        s3 = create_s3_client(region, profile_name)
        if not s3:
            logger.error("Failed to create S3 client")
            return None, None
            
        # List objects with the specified prefix
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        
        # Filter objects based on exclude pattern
        csv_files = []
        for obj in response.get('Contents', []):
            key = obj['Key']
            if key.lower().endswith('.csv') and exclude_pattern not in key.lower():
                # Add object metadata including LastModified
                csv_files.append({
                    'Key': key,
                    'LastModified': obj['LastModified'],
                    'Size': obj['Size'],
                    'ETag': obj['ETag']
                })
        
        # Sort files by LastModified (oldest first for idempotent operation)
        csv_files.sort(key=lambda x: x['LastModified'])
        
        logger.info(f"Found {len(csv_files)} CSV files to merge")
        for f in csv_files:
            logger.info(f"  - {f['Key']} (Last modified: {f['LastModified']})")
        
        if not csv_files:
            logger.warning("No CSV files found to merge")
            return None, None
        
        # Create output key if not provided
        if not output_key:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            output_key = f"{prefix.rstrip('/')}/merged-{timestamp}.csv"
        
        # Generate a hash of source files for idempotency check
        source_files_hash = hashlib.md5()
        for file_info in csv_files:
            hash_str = f"{file_info['Key']}|{file_info['ETag']}|{file_info['Size']}|{file_info['LastModified'].isoformat()}"
            source_files_hash.update(hash_str.encode())
        source_hash_hex = source_files_hash.hexdigest()
        
        # Check if output file and hash already exist
        hash_key = f"{output_key}.hash"
        try:
            if not force:
                # Try to get existing hash file
                hash_obj = s3.get_object(Bucket=bucket_name, Key=hash_key)
                existing_hash = hash_obj['Body'].read().decode('utf-8').strip()
                
                # If hash matches, files haven't changed
                if existing_hash == source_hash_hex:
                    logger.info(f"Source files unchanged since last merge. Using existing file: {output_key}")
                    
                    # Download a local copy if requested
                    local_file_path = None
                    if local_output_dir:
                        local_file_path = os.path.join(local_output_dir, os.path.basename(output_key))
                        # Ensure output directory exists
                        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                        
                        try:
                            # Download the merged file from S3
                            s3.download_file(bucket_name, output_key, local_file_path)
                            logger.info(f"Downloaded existing merged file to {local_file_path}")
                        except Exception as e:
                            logger.error(f"Error downloading merged file: {str(e)}")
                            local_file_path = None
                    
                    return output_key, local_file_path
        except s3.exceptions.NoSuchKey:
            # Hash file doesn't exist, we'll create it later
            pass
        except Exception as e:
            logger.warning(f"Error checking hash file: {str(e)}")
        
        # Read all CSV files from S3
        all_data = []
        header = None
        
        for i, file_info in enumerate(csv_files):
            key = file_info['Key']
            logger.info(f"Processing file {i+1}/{len(csv_files)}: {key}")
            
            try:
                # Get file content
                response = s3.get_object(Bucket=bucket_name, Key=key)
                content = response['Body'].read().decode('utf-8')
                
                # Parse CSV content
                csv_reader = csv.reader(io.StringIO(content))
                rows = list(csv_reader)
                
                if not rows:
                    logger.warning(f"File {key} is empty")
                    continue
                
                if header is None:
                    # First file with content provides the header
                    header = rows[0]
                    all_data.append(rows)
                else:
                    # For subsequent files, check if header matches
                    if rows[0] != header:
                        logger.warning(f"Header in {key} doesn't match reference header.")
                        logger.warning(f"Expected: {header}")
                        logger.warning(f"Found: {rows[0]}")
                    all_data.append(rows)
            
            except Exception as e:
                logger.error(f"Error processing S3 file {key}: {str(e)}")
                # Continue with other files
        
        if not all_data:
            logger.error("No valid data found in any CSV file")
            return None, None
        
        # Merge data preserving order of files (oldest first)
        merged_rows = []
        
        # Add header from first file
        if header:
            merged_rows.append(header)
        
        # Use ordered dictionary to maintain the order of insertion while ensuring uniqueness by ARN
        unique_rows = OrderedDict()
        
        # Process all files in order
        for file_data in all_data:
            # Skip the header row (first row) of each file
            for row in file_data[1:]:
                if len(row) > 1:  # Ensure row has the ARN column
                    # Use ARN (second column) as the unique key
                    arn = row[1]
                    # Only add if this ARN hasn't been seen before
                    # Last occurrence of each ARN will be preserved
                    unique_rows[arn] = row
        
        # Add all unique rows to result
        merged_rows.extend(unique_rows.values())
        
        # Convert merged rows to CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(merged_rows)
        merged_content = output.getvalue()
        
        # Create local copy if a directory is specified
        local_file_path = None
        if local_output_dir:
            try:
                # Ensure output directory exists
                os.makedirs(local_output_dir, exist_ok=True)
                
                # Create local file path
                local_file_path = os.path.join(local_output_dir, os.path.basename(output_key))
                
                # Write merged content to local file
                with open(local_file_path, 'w', newline='') as f:
                    f.write(merged_content)
                
                logger.info(f"Saved local copy of merged file to {local_file_path}")
            except Exception as e:
                logger.error(f"Error saving local copy: {str(e)}")
                local_file_path = None
        
        # Write merged content to S3
        try:
            s3.put_object(
                Bucket=bucket_name,
                Key=output_key,
                Body=merged_content.encode('utf-8')
            )
            logger.info(f"Successfully uploaded merged file to s3://{bucket_name}/{output_key}")
            
            # Write hash file for idempotency
            s3.put_object(
                Bucket=bucket_name,
                Key=hash_key,
                Body=source_hash_hex.encode('utf-8')
            )
            logger.info(f"Created hash file at s3://{bucket_name}/{hash_key}")
            
            logger.info(f"Successfully merged {len(csv_files)} files with {len(unique_rows)} unique records")
            
            # Code to remove versioned files (commented out as requested)
            """
            # Remove the versioned files that were merged
            logger.info(f"Removing {len(csv_files)} source files that were merged")
            for file_info in csv_files:
                key = file_info['Key']
                try:
                    s3.delete_object(Bucket=bucket_name, Key=key)
                    logger.info(f"Deleted source file: s3://{bucket_name}/{key}")
                except Exception as e:
                    logger.error(f"Error deleting source file {key}: {str(e)}")
            """
            
            return output_key, local_file_path
            
        except Exception as e:
            logger.error(f"Error uploading merged file to S3: {str(e)}")
            return None, None
        
    except Exception as e:
        logger.error(f"Error merging CSV files from S3: {str(e)}")
        return None, None

