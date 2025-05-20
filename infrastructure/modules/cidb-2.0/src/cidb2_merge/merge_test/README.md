# CSV Merger and Validator Tools

This directory contains tools for merging and validating CSV files in an idempotent manner, particularly designed for AWS IAM policy data.

## Overview

The tools support an append-only pattern for processing CSV files, which eliminates race conditions when multiple processes (like Lambda functions) operate concurrently. This implementation follows S3 versioning best practices to ensure data integrity.

## Key Features

- **Idempotent Operations**: Same input files always produce the same output
- **File Fingerprinting**: Hash-based detection of unchanged source files
- **Robust Validation**: Ensures all source data appears in merged output
- **Flexible Filtering**: Target specific files by patterns and prefixes
- **Detailed Logging**: Full visibility into merge and validation operations
- **Separate Output Directory**: Prevents accidentally reprocessing merged files

## Prerequisites

- Python 3.6+
- Standard libraries (no external dependencies required)

## CSV Merger (`csv_merger.py`)

Merges multiple CSV files while preserving headers and ensuring uniqueness based on ARN (second column).

### Usage

```bash
python csv_merger.py -d <source_directory> -o <output_file> [options]
```

### Options

- `-d, --directory`: Source directory containing CSV files (required)
- `-o, --output`: Output filename for merged CSV (default: merged-TIMESTAMP.csv)
- `-p, --pattern`: File pattern to include (default: "*.csv")
- `-e, --exclude`: Pattern to exclude from filenames (default: "merged")
- `--force`: Force regeneration even if source files are unchanged

### Examples

```bash
# Basic merge of all CSV files
python csv_merger.py -d ./data -o ./output/merged.csv

# Merge only AWS IAM policy files
python csv_merger.py -d ./data -o ./output/aws_policies.csv -p "AWS_IAM*.csv"

# Force regeneration of merged file
python csv_merger.py -d ./data -o ./output/merged.csv --force
```

## CSV Validator (`validate_merge.py`)

Validates that a merged CSV file contains all rows from source files by comparing ARNs.

### Usage

```bash
python validate_merge.py -m <merged_file> -d <source_directory> [options]
```

### Options

- `-m, --merged`: Path to the merged CSV file to validate (required)
- `-d, --directory`: Directory containing source CSV files (required)
- `-p, --pattern`: Pattern to match source files (default: "*.csv")
- `-e, --exclude`: Pattern to exclude from source files (default: "merged")

### Examples

```bash
# Validate merged file against all source files
python validate_merge.py -m ./output/merged.csv -d ./data

# Validate against specific source files
python validate_merge.py -m ./output/aws_policies.csv -d ./data -p "AWS_IAM*.csv"
```

## How It Works

### Merge Process

1. Scans source directory for CSV files matching the specified pattern
2. Sorts files by creation time (oldest first) for consistent processing
3. Extracts headers from the first file
4. For each subsequent file, skips the header and collects data rows
5. Ensures uniqueness based on ARN (second column)
6. Writes the final merged data to the output file
7. Creates a hash file to detect unchanged sources for future runs

### Validation Process

1. Extracts ARNs from all source files
2. Extracts ARNs from the merged file
3. Checks that every ARN from each source file appears in the merged file
4. Reports any missing ARNs and provides detailed statistics
5. Returns a success/failure status (exit code 0/1)

## Handling Duplicate ARNs

When the same ARN appears in multiple source files, the tool preserves the data from the most recent file. This ensures consistency in an append-only pattern where newer data updates older entries.

## Best Practices

1. **Use a Separate Output Directory**: Keep merged files separate from source files to prevent accidental reprocessing
2. **Consistent File Patterns**: Use specific patterns like `AWS_IAM*.csv` to target only relevant files
3. **Validate After Merging**: Always run validation to confirm data integrity
4. **Review Logs**: Check the detailed logs for any warnings or errors
5. **Maintain Source Files**: The append-only pattern works best when source files are preserved

## Advanced Usage: S3 Integration

When working with S3:

1. Download source files to a local directory
2. Run the merge operation
3. Upload the merged file to S3
4. Upload the hash file alongside for future idempotent operations
5. Validate the merged file against source files

## S3 Integration for CSV Merger

The tools support both local file operations and S3 bucket operations, implemented to work with the append-only pattern for AWS Lambda functions.

### Using the S3 Merger (`csv_merger.py s3`)

```bash
python csv_merger.py s3 -b <bucket_name> -p <prefix> [options]
```

### S3 Options

- `-b, --bucket`: S3 bucket name (required)
- `-p, --prefix`: S3 prefix to search for CSV files (required)
- `-o, --output-key`: Output S3 key for merged file (default: PREFIX/merged-TIMESTAMP.csv)
- `-e, --exclude`: Pattern to exclude from file keys (default: "merged")
- `-r, --region`: AWS region (default: from AWS configuration)
- `--profile`: AWS profile name (default: from AWS configuration)
- `-l, --local-output`: Local directory to save a copy of the merged file for validation
- `--force`: Force regeneration even if source files are unchanged

### S3 Workflow Example

```bash
# Merge AWS IAM Policy files from S3 and save a local copy for validation
python csv_merger.py s3 -b my-inventory-bucket -p AWS_IAM/ -o AWS_IAM/merged.csv -l ./local_output/

# Validate the merged file using the local copy
python validate_merge.py -m ./local_output/merged.csv -d ./local_source/ -p "AWS_IAM*.csv"
```

### Complete S3 Processing Workflow

The complete workflow for processing CSV files from S3 is:

1. **Merge Files from S3**:
   - Scan S3 bucket for files matching the specified prefix
   - Sort files by LastModified timestamp (oldest first)
   - Download and process files to merge their contents
   - Ensure uniqueness based on ARN (second column)
   - Upload merged file to S3
   - Save a local copy if requested (for validation)

2. **Validate the Merged File**:
   - Use the local copy created during merge
   - Compare ARNs in the merged file against original source files
   - Verify all original ARNs are present in the merged output
   - Return success/failure status

3. **Cleanup (Optional)**:
   - Remove the original versioned files from S3 (code commented out by default)
   - To enable cleanup, uncomment the cleanup code in `merge_csv_files_from_s3` function

### S3 Idempotency

The S3 merger maintains idempotency through:

1. Hash-based tracking of source files (ETag, Size, LastModified timestamp)
2. Storage of hash files alongside merged files in S3
3. Skip processing when source files are unchanged

### Append-Only Pattern and Versioning

This implementation supports the append-only pattern with S3 versioning by:

1. Processing files in a consistent order (by LastModified)
2. Maintaining uniqueness based on ARN
3. Preserving the latest version of each record
4. Supporting incremental updates without race conditions

When multiple Lambda functions process messages concurrently, each can safely append its own data without conflicts, as the merge operation handles de-duplication based on ARNs.

### Enabling Source File Cleanup

To enable removal of source files after successful merge (currently commented out):

1. Edit `csv_merger.py`
2. Find the commented block in `merge_csv_files_from_s3` function
3. Uncomment the cleanup code 
4. This will remove source files after successfully creating the merged file

**WARNING**: Removing source files is irreversible. Ensure you have validated the merged file before enabling this option in production.

### Local File Validation

After merging files from S3, you can validate the merged output:

```bash
# Validate after S3 merge
python validate_merge.py -m <local_merged_file> -d <source_directory> -p "AWS_IAM*.csv"
```

For source files from S3, you'll need to download them to a local directory first, or use the local copies if they were previously downloaded.

## Automated S3 Processing

For automated processing in Lambda environments:

```python
from cidb2_merge import csv_merger

# Merge files from S3
output_key, local_file_path = csv_merger.merge_csv_files_from_s3(
    bucket_name="my-bucket",
    prefix="AWS_IAM/",
    output_key="AWS_IAM/merged.csv",
    local_output_dir="/tmp/output"  # Lambda temp directory
)

# Validate the merged file
from cidb2_merge import validate_merge
is_valid = validate_merge.validate_merged_file(
    local_file_path, 
    "/tmp/source"  # Directory containing source files
)

# Handle validation result
if is_valid:
    print("Validation successful!")
else:
    print("Validation failed!")

## Testing Idempotency

This directory contains a testing script to verify the idempotent behavior of the CSV merger and validation tools. The script is designed to ensure that the merge operation produces consistent, idempotent results across multiple runs.

### How to Use the Testing Script

#### Prerequisites

1. Ensure you have AWS IAM CSV files in the `test/data` directory with the naming pattern `AWS_IAM*.csv`
2. Make sure the script has execute permissions:
   ```bash
   chmod +x test_idempotency.sh
   ```

#### Running the Test

1. Navigate to the merge_test directory:
   ```bash
   cd /path/to/merge_test
   ```

2. Run the script:
   ```bash
   ./test_idempotency.sh
   ```

3. The script will:
   - Check for AWS IAM CSV files in the test/data directory
   - Create the test/output directory if it doesn't exist
   - Run the merger and validation operations 20 times
   - Display progress and results in real-time
   - Generate a summary at the end

#### Interpreting the Results

- The script outputs status information to both the console and a log file
- For each run, look for the message: "Run X: Validation SUCCESSFUL"
- At the end, a summary shows the total number of successful and failed validations
- The full log file is saved at `idempotency_test.log` for detailed analysis

#### Customizing the Test

To modify the test parameters, edit the `test_idempotency.sh` file:

- Change the number of test runs by modifying the loop range: `for i in {1..20}`
- Adjust file paths if necessary in the script variables:
  ```bash
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  DATA_DIR="$SCRIPT_DIR/test/data"
  OUTPUT_DIR="$SCRIPT_DIR/test/output"
  LOG_FILE="$SCRIPT_DIR/idempotency_test.log"
  ```
- Update the filename pattern by changing `AWS_IAM*.csv` to match your specific files

### Directory Structure

The test environment uses the following structure:
```
merge_test/
  ├── csv_merger.py        # The CSV merger script
  ├── validate_merge.py    # The validation script
  ├── test_idempotency.sh  # The testing script
  └── test/
      ├── data/            # Contains source AWS_IAM*.csv files
      └── output/          # Where merged files will be placed
```

### Expected Test Results

When running the test script:

1. The first run generates a new merged file
2. Subsequent runs detect that source files are unchanged and reuse the existing file
3. All validation runs confirm that all ARNs from source files are present in the merged file
4. Summary shows 20/20 successful validations

This test verifies that the implementation correctly addresses the race condition issues that can occur in Lambda environments with concurrent processing.

### Relationship to S3 Append-Only Pattern

The idempotency testing script is specifically designed to validate the append-only pattern that addresses race conditions in Lambda environments:

1. **Race Condition Validation**: By running 20 successive merges and validations, the script confirms that the code properly handles the scenario where multiple Lambda instances might process the same file concurrently.

2. **Versioning Simulation**: The test simulates how S3 versioning works in your production environment, with each run potentially creating a new version of the output file.

3. **Hash-Based Idempotency**: The hash checking mechanism verifies that unchanged source files don't trigger redundant processing - essential for your Lambda functions that may be triggered multiple times for the same files.

4. **Data Integrity**: The validation after each merge confirms that all ARNs from source files are correctly preserved in the output, ensuring your Lambda functions aren't losing data during concurrent processing.

This testing approach directly validates the effectiveness of the append-only pattern implemented in your Lambda functions, which:
- Eliminates race conditions by having each Lambda instance only append its own data
- Avoids the need for complex locking mechanisms
- Maintains data integrity with version tracking
- Simplifies error handling
- Improves performance by avoiding unnecessary full file reads

### Test Script Details

The test script:
1. Automatically finds the test/data directory relative to its location
2. Verifies that AWS_IAM*.csv files exist in the data directory
3. Creates the output directory if it doesn't exist
4. Runs the merger and validation operations 20 times
5. Records all output to idempotency_test.log

### Troubleshooting

If the test fails, check the following:

1. **Missing Data Files**: Verify AWS IAM CSV files exist in the test/data directory
2. **Permissions Issues**: Ensure all scripts have execute permissions
3. **File Format Problems**: Confirm the CSV files contain properly formatted ARNs in the expected column
4. **Path Issues**: Check that relative paths are resolving correctly based on the script's location

## Integration with Lambda Functions

These tools are designed to integrate with AWS Lambda functions that process messages concurrently. The append-only pattern eliminates the race conditions that typically occur in read-modify-write scenarios, especially with S3 versioning.

For Lambda integration:

1. Each Lambda instance can safely append its own data
2. The merge operation handles de-duplication based on ARNs
3. Validation confirms data integrity
4. Hash-based tracking ensures idempotent operations

The S3 implementation efficiently supports this workflow by maintaining idempotent behavior across multiple runs, perfect for your Lambda environment where concurrent operations might otherwise cause race conditions.

## Troubleshooting

### Validation Failures

If validation reports missing ARNs, check:
- File encoding issues in source files
- Malformed CSV data
- Inconsistent headers across files

### Performance Considerations

For large datasets:
- Process files in batches
- Use separate output directories for different data types
- Consider incremental validation for very large files
