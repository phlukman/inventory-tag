#!/usr/bin/env python3
import json
import urllib.parse
import csv
import sys
import argparse
import os

def validate_json(json_string):
    """
    Validate if a string is valid JSON
    
    Args:
        json_string (str): The string to validate
        
    Returns:
        tuple: (is_valid, parsed_data_or_error_message)
    """
    try:
        data = json.loads(json_string)
        print("✓ JSON is valid")
        return True, data
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON: {e}"
        print(f"✗ {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error validating JSON: {e}"
        print(f"✗ {error_msg}")
        return False, error_msg

def decode_aws_config_policy(json_string):
    """
    Decode URL-encoded policy documents in AWS Config JSON strings.
    
    Args:
        json_string (str): The JSON string containing encoded policy documents
        
    Returns:
        tuple: (success, decoded_data_or_error)
    """
    print(f"Input JSON length: {len(json_string)} characters")
    
    # First validate the JSON
    is_valid, data_or_error = validate_json(json_string)
    if not is_valid:
        return False, data_or_error
    
    data = data_or_error
    
    try:
        # Check if this is an IAM Policy resource type
        resource_type = data.get('resourceType')
        print(f"Resource type: {resource_type}")
        
        if resource_type == 'AWS::IAM::Policy':
            print("✓ Found IAM Policy resource")
            
            # Parse the nested configuration JSON
            config_str = data.get('configuration')
            if not config_str:
                return False, "No 'configuration' field found in JSON"
            
            try:
                config = json.loads(config_str)
                print("✓ Configuration JSON parsed successfully")
            except json.JSONDecodeError as e:
                return False, f"Invalid configuration JSON: {e}"
            
            # Check if policyVersionList exists
            if 'policyVersionList' in config and config['policyVersionList']:
                print(f"✓ Found {len(config['policyVersionList'])} policy versions")
                
                # Iterate through all policy versions
                for i, policy_version in enumerate(config['policyVersionList']):
                    if 'document' in policy_version:
                        print(f"Processing policy version {i}")
                        
                        # Get the URL-encoded document
                        encoded_doc = policy_version['document']
                        print(f"Encoded document length: {len(encoded_doc)} characters")
                        
                        # Check if it's URL-encoded
                        if '%' in encoded_doc:
                            print("✓ Found URL-encoded content, decoding...")
                            # Decode the URL-encoded string
                            decoded_doc = urllib.parse.unquote(encoded_doc)
                            print(f"Decoded document length: {len(decoded_doc)} characters")
                            
                            # Parse the decoded JSON to get the policy
                            try:
                                policy = json.loads(decoded_doc)
                                print("✓ Policy document parsed successfully")
                                
                                # Replace the encoded document with the decoded policy
                                policy_version['document'] = policy
                            except json.JSONDecodeError as e:
                                print(f"✗ Error parsing decoded policy document: {e}")
                                return False, f"Invalid policy document JSON: {e}"
                        else:
                            print("Document is not URL-encoded, leaving as-is")
                
                # Update the configuration as an object, not a string
                data['configuration'] = config
                print("✓ Configuration updated with decoded policies")
            else:
                print("! No policyVersionList found in configuration")
        else:
            print(f"! Not an IAM Policy (resource type: {resource_type})")
            print("Returning original data without decoding")
        
        return True, data
        
    except Exception as e:
        error_msg = f"Unexpected error during decoding: {e}"
        print(f"✗ {error_msg}")
        import traceback
        traceback.print_exc()
        return False, error_msg

def write_to_csv(data, output_file, script_dir):
    """
    Write data to CSV file in the output directory
    
    Args:
        data: The data to write (can be dict, list, or error message)
        output_file (str): The output filename
        script_dir (str): The directory where the script is located
        
    Returns:
        bool: Success status
    """
    # Create output directory relative to script location
    output_dir = os.path.join(script_dir, 'output')
    
    print(f"Script directory: {script_dir}")
    print(f"Creating output directory: {output_dir}")
    
    # Create directory
    try:
        os.makedirs(output_dir, exist_ok=True)
        print("✓ Output directory created/verified")
    except Exception as e:
        print(f"✗ Error creating output directory: {e}")
        return False
    
    # Prepare the output path
    full_output_path = os.path.join(output_dir, output_file)
    print(f"Writing to: {full_output_path}")
    
    # Convert data to JSON string for CSV
    if isinstance(data, (dict, list)):
        output_content = json.dumps(data, indent=2)
    else:
        # If it's an error message, write it as-is
        output_content = str(data)
    
    # Write to CSV file
    try:
        with open(full_output_path, 'w', newline='', encoding='utf-8') as csvfile:
            # Write header manually
            csvfile.write('Status,Content\n')
            
            # Determine status
            status = 'SUCCESS' if isinstance(data, (dict, list)) else 'ERROR'
            
            # Write the data without CSV quoting to avoid double quotes
            csvfile.write(f'{status},"{output_content}"\n')
        
        print(f"✓ Data written to {full_output_path}")
        
        # Verify file creation
        if os.path.exists(full_output_path):
            file_size = os.path.getsize(full_output_path)
            print(f"✓ File verified, size: {file_size} bytes")
            return True
        else:
            print(f"✗ File verification failed")
            return False
            
    except Exception as e:
        print(f"✗ Error writing to file: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Decode URL-encoded JSON and write to CSV')
    
    # Add arguments
    parser.add_argument('json_input', nargs='?', help='The encoded JSON string to decode (or read from stdin if omitted)')
    parser.add_argument('-o', '--output', default='decoded_output.json', 
                       help='Output file name (default: decoded_output.json)')
    parser.add_argument('-f', '--file', action='store_true',
                       help='Treat json_input as a file path instead of a JSON string')
    parser.add_argument('--csv', action='store_true',
                       help='Output as CSV instead of JSON')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Get the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Script location: {script_dir}")
    
    # Adjust output filename based on format choice
    if args.csv and not args.output.endswith('.csv'):
        args.output = args.output.replace('.json', '.csv') if args.output.endswith('.json') else args.output + '.csv'
    elif not args.csv and not args.output.endswith('.json'):
        args.output = args.output.replace('.csv', '.json') if args.output.endswith('.csv') else args.output + '.json'
    
    # Get JSON input
    json_input = None
    
    if not args.json_input:
        # Read from stdin
        print("Reading JSON from stdin...")
        json_input = sys.stdin.read().strip()
    elif args.file:
        # Read from file
        print(f"Reading from file: {args.json_input}")
        try:
            with open(args.json_input, 'r', encoding='utf-8') as f:
                json_input = f.read().strip()
            
            if not json_input:
                print(f"✗ File '{args.json_input}' is empty")
                write_to_csv("Error: Input file is empty", args.output, script_dir)
                sys.exit(1)
            
            print(f"✓ Read {len(json_input)} characters from file")
            
        except FileNotFoundError:
            error_msg = f"Error: File '{args.json_input}' not found"
            print(f"✗ {error_msg}")
            write_to_csv(error_msg, args.output, script_dir)
            sys.exit(1)
        except Exception as e:
            error_msg = f"Error reading file: {e}"
            print(f"✗ {error_msg}")
            write_to_csv(error_msg, args.output, script_dir)
            sys.exit(1)
    else:
        # Use as direct JSON string
        print("Using command line argument as JSON string")
        json_input = args.json_input
    
    # Process the JSON
    print("\n=== Processing JSON ===")
    success, result = decode_aws_config_policy(json_input)
    
    # Write results to CSV
    print(f"\n=== Writing results to CSV ===")
    if write_to_csv(result, args.output, script_dir):
        if success:
            print(f"\n✓ SUCCESS: Decoded JSON written to output/{args.output}")
        else:
            print(f"\n! ERROR: Error details written to output/{args.output}")
    else:
        print(f"\n✗ FAILED: Could not write to output file")
        sys.exit(1)

if __name__ == "__main__":
    main()