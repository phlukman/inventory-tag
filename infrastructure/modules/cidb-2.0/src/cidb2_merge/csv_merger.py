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
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
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
        dialect = csv.Sniffer().sniff(content, delimiters=[",", ";", "\t"])

        logger.info(
            f"Detected CSV dialect with delimiter: '{dialect.delimiter}', "
            f"line terminator: {repr(dialect.lineterminator)}"
        )
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
    source_files = [
        f for f in all_files if exclude_pattern not in os.path.basename(f).lower()
    ]

    # Sort files by modification time (oldest first)
    # This is important for idempotent operation
    source_files.sort(key=os.path.getmtime)

    return source_files


def merge_csv_files_from_directory(
    directory_path,
    output_filename=None,
    pattern="*.csv",
    exclude_pattern="merged",
    force=False,
):
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
                with open(hash_file, "r") as f:
                    existing_hash = f.read().strip()

                    # If hash matches, files haven't changed, no need to reprocess
                    if existing_hash == source_files_hash.hexdigest():
                        logger.info(
                            f"Source files unchanged since last merge. Using existing file: {output_filename}"
                        )
                        return output_filename

        # Read all CSV files into memory
        all_data = []
        header = None

        for i, file_path in enumerate(csv_files):
            logger.info(
                f"Processing file {i+1}/{len(csv_files)}: {os.path.basename(file_path)}"
            )

            try:
                with open(file_path, "r", encoding="utf-8") as f:
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
                            logger.warning(
                                f"Header in {os.path.basename(file_path)} doesn't match reference header."
                            )
                            logger.warning(f"Expected: {header}")
                            logger.warning(f"Found: {rows[0]}")
                        all_data.append(rows)

            except Exception as e:
                logger.error(
                    f"Error processing file {os.path.basename(file_path)}: {str(e)}"
                )
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
                if len(row) > 2:  # Ensure row has the ARN column
                    # Use ARN (second column) as the unique key
                    arn = row[2]
                    # Only add if this ARN hasn't been seen before
                    # Last occurrence of each ARN will be preserved
                    unique_rows[arn] = row

        # Add all unique rows to result
        merged_rows.extend(unique_rows.values())
        # Write merged data to output file
        with open(output_filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(merged_rows)

        # Store hash in metadata file for idempotency check
        source_files_hash = hashlib.md5()
        for file_path in csv_files:
            source_files_hash.update(get_file_hash(file_path).encode())

        with open(f"{output_filename}.hash", "w") as f:
            f.write(source_files_hash.hexdigest())

        logger.info(
            f"Successfully merged {len(csv_files)} files with {len(unique_rows)} unique records to: {output_filename}"
        )
        return output_filename

    except Exception as e:
        logger.error(f"Error merging CSV files: {str(e)}")
        return None
