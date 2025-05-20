#!/usr/bin/python
"""
Validate Merged CSV Files

This script validates that a merged CSV file contains all rows from the source CSV files.
It compares ARNs (the second column) from source files with those in the merged file
to ensure nothing is missing.
"""
import os
import csv
import logging
import glob
import argparse
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def validate_merge(merged_file, source_directory, pattern="*.csv", exclude_pattern="merged"):
    """
    Validate that a merged CSV file contains all rows from source CSV files.
    
    Args:
        merged_file (str): Path to the merged CSV file
        source_directory (str): Directory containing source CSV files
        pattern (str): Pattern to match source files 
        exclude_pattern (str): Pattern to exclude from source files
        
    Returns:
        tuple: (is_valid, missing_arns, source_arns_count, merged_arns_count)
    """
    # Check if merged file exists
    if not os.path.exists(merged_file):
        logger.error(f"Merged file not found: {merged_file}")
        return False, [], 0, 0
    
    # Find all source CSV files
    all_files = glob.glob(os.path.join(source_directory, pattern))
    
    # Filter out files containing the exclude pattern and the merged file itself
    merged_filename = os.path.basename(merged_file)
    source_files = [
        f for f in all_files 
        if exclude_pattern not in os.path.basename(f).lower() 
        and os.path.basename(f) != merged_filename
    ]
    
    if not source_files:
        logger.warning("No source CSV files found to validate against")
        return False, [], 0, 0
    
    # Track ARNs from source files and which file they came from
    source_arns = {}
    arns_by_file = defaultdict(set)
    
    # Read ARNs from all source files
    for file_path in source_files:
        filename = os.path.basename(file_path)
        logger.info(f"Checking source file: {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                # Skip header
                next(reader, None)
                
                # Read all rows and extract ARNs (second column)
                row_count = 0
                for row in reader:
                    if len(row) > 1:
                        arn = row[1]
                        source_arns[arn] = file_path
                        arns_by_file[filename].add(arn)
                        row_count += 1
                
                logger.info(f"  - Found {row_count} ARNs in {filename}")
        
        except Exception as e:
            logger.error(f"Error reading source file {filename}: {str(e)}")
    
    # Read ARNs from merged file
    merged_arns = set()
    try:
        with open(merged_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            # Skip header
            next(reader, None)
            
            # Read all rows and extract ARNs (second column)
            for row in reader:
                if len(row) > 1:
                    merged_arns.add(row[1])
    
    except Exception as e:
        logger.error(f"Error reading merged file: {str(e)}")
        return False, [], len(source_arns), 0
    
    # Find missing ARNs
    missing_arns = []
    for arn, file_path in source_arns.items():
        if arn not in merged_arns:
            missing_arns.append((arn, os.path.basename(file_path)))
    
    # Additional validation for each source file
    for filename, arns in arns_by_file.items():
        missing_in_file = [arn for arn in arns if arn not in merged_arns]
        if missing_in_file:
            logger.error(f"File {filename} has {len(missing_in_file)} ARNs missing from merged file")
        else:
            logger.info(f"✓ All {len(arns)} ARNs from {filename} are present in merged file")
    
    # Log summary statistics
    logger.info(f"Total ARNs in source files: {len(source_arns)}")
    logger.info(f"Total ARNs in merged file: {len(merged_arns)}")
    
    # Determine if validation passed
    is_valid = len(missing_arns) == 0
    
    return is_valid, missing_arns, len(source_arns), len(merged_arns)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Validate that merged CSV contains all rows from source files')
    parser.add_argument('-m', '--merged', type=str, required=True, 
                        help='Path to the merged CSV file to validate')
    parser.add_argument('-d', '--directory', type=str, required=True, 
                        help='Directory containing source CSV files')
    parser.add_argument('-p', '--pattern', type=str, default="*.csv",
                        help='Pattern to match source files (default: *.csv)')
    parser.add_argument('-e', '--exclude', type=str, default="merged",
                        help='Pattern to exclude from source files (default: merged)')
    
    return parser.parse_args()

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()
    
    logger.info(f"Validating {args.merged} against source files in {args.directory}")
    
    # Validate the merge
    is_valid, missing_arns, source_count, merged_count = validate_merge(
        args.merged, 
        args.directory,
        args.pattern,
        args.exclude
    )
    
    # Print missing ARNs if any
    if missing_arns:
        logger.error(f"Found {len(missing_arns)} ARNs missing from merged file:")
        for i, (arn, filename) in enumerate(missing_arns[:10]):  # Limit output to first 10
            logger.error(f"  {i+1}. ARN: {arn} (from {filename})")
        
        if len(missing_arns) > 10:
            logger.error(f"  ... and {len(missing_arns) - 10} more")
    
    # Print final result
    if is_valid:
        logger.info("✅ VALIDATION SUCCESSFUL: All ARNs from source files are present in the merged file")
        logger.info(f"   Merged file contains {merged_count} unique ARNs from {source_count} source ARNs")
        exit(0)
    else:
        logger.error("❌ VALIDATION FAILED: Some ARNs from source files are missing in the merged file")
        logger.error(f"   {len(missing_arns)} ARNs missing out of {source_count} total source ARNs")
        exit(1)
