#!/bin/bash
# Script to test idempotency of CSV merger and validation

# Use script directory as the reference point
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/test/data"
OUTPUT_DIR="$SCRIPT_DIR/test/output"
LOG_FILE="$SCRIPT_DIR/idempotency_test.log"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Verify that the data directory exists and has files
if [ ! -d "$DATA_DIR" ] || [ $(ls "$DATA_DIR"/AWS_IAM*.csv 2>/dev/null | wc -l) -eq 0 ]; then
  echo "Error: Data directory does not exist or contains no AWS IAM CSV files."
  echo "Expected data files in: $DATA_DIR"
  exit 1
fi

# Count source files
CSV_COUNT=$(ls "$DATA_DIR"/AWS_IAM*.csv 2>/dev/null | wc -l)
echo "Found $CSV_COUNT AWS IAM CSV files in $DATA_DIR"

# Clear log file
echo "Starting idempotency test at $(date)" > $LOG_FILE

# Run 20 times and check for consistent results
for i in {1..20}; do
    echo "===== Run $i =====" | tee -a $LOG_FILE
    
    # Run merger with local command
    echo "Running merger..." | tee -a $LOG_FILE
    python csv_merger.py local -d "$DATA_DIR" -o "$OUTPUT_DIR/merged-test.csv" -p "AWS_IAM*.csv" | tee -a $LOG_FILE
    
    # Check file size
    FILESIZE=$(wc -l < "$OUTPUT_DIR/merged-test.csv")
    echo "Merged file has $FILESIZE lines" | tee -a $LOG_FILE
    
    # Run validation
    echo "Running validation..." | tee -a $LOG_FILE
    python validate_merge.py -m "$OUTPUT_DIR/merged-test.csv" -d "$DATA_DIR" -p "AWS_IAM*.csv" | tee -a $LOG_FILE
    
    # Check validation exit code
    if [ $? -eq 0 ]; then
        echo " Run $i: Validation SUCCESSFUL" | tee -a $LOG_FILE
    else
        echo " Run $i: Validation FAILED" | tee -a $LOG_FILE
    fi
    
    echo "" | tee -a $LOG_FILE
done

# Report final results
echo "===== SUMMARY =====" | tee -a $LOG_FILE
echo "Completed 20 runs of merge and validation" | tee -a $LOG_FILE
grep "Validation" $LOG_FILE | grep -c "SUCCESSFUL" | xargs -I{} echo "Successful validations: {}" | tee -a $LOG_FILE
grep "Validation" $LOG_FILE | grep -c "FAILED" | xargs -I{} echo "Failed validations: {}" | tee -a $LOG_FILE
grep "unique records" $LOG_FILE | tail -n 1 | tee -a $LOG_FILE

echo "See $LOG_FILE for complete output" | tee -a $LOG_FILE
