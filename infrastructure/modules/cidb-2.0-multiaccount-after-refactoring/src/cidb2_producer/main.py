"""
CIDB2 Producer - Lambda handlers for AWS inventory collection
"""
import json
import logging
import os
from typing import Dict, List, Any, Optional
import boto3
from cidb2_producer import (
    SnsPublisher, 
    AwsAccountCollector,
    IamPolicyCollector,
    KmsKeyCollector,
    Ec2InstanceCollector,
    S3BucketCollector
)

# Set up logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Environment Variables
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")
SERVICE_TYPE = os.environ.get("SERVICE_TYPE")
DEFAULT_BATCH_SIZE = int(os.environ.get("DEFAULT_BATCH_SIZE", "10"))
LARGE_BATCH_SIZE = int(os.environ.get("LARGE_BATCH_SIZE", "20"))
LARGE_BATCH_THRESHOLD = int(os.environ.get("LARGE_BATCH_THRESHOLD", "100"))

# The role name to assume in target accounts
COLLECTOR_ROLE_NAME = "CIDB2-Collector-Role"


def lambda_handler(event, context):
    """
    Lambda handler for CIDB2 inventory collection
    
    Args:
        event: Lambda event from Step Functions
        context: Lambda context
        
    Returns:
        Dict: Results of the collection
    """
    logger.info("Starting CIDB2 inventory collection")
    logger.debug(f"Event: {json.dumps(event)}")
    
    # Extract parameters from the event
    service = event.get("service", SERVICE_TYPE)
    accounts = event.get("accounts", [])
    config = event.get("config", {})
    execution_id = event.get("execution_id", context.aws_request_id)
    
    if not accounts:
        logger.error("No accounts provided for collection")
        return {
            "status": "failed",
            "error": "No accounts provided for collection"
        }
    
    logger.info(f"Collecting {service} data from {len(accounts)} accounts")
    
    # Initialize the collector with the specified role name
    collector = AwsAccountCollector(
        role_name=COLLECTOR_ROLE_NAME,
        region=os.environ.get("AWS_REGION", "us-east-1")
    )
    
    # Collect data from the specified accounts
    results = collector.collect_from_accounts(accounts, service)
    
    # Publish results to SNS
    if SNS_TOPIC_ARN:
        # Prepare data for SNS publishing
        items_to_publish = prepare_items_for_sns(results, service, execution_id)
        
        if items_to_publish:
            # Set up SNS publisher
            sns_publish_data = SnsPublisher()
            
            # Set up common attributes for all messages
            common_attributes = {
                "service": {
                    "DataType": "String",
                    "StringValue": service
                },
                "execution_id": {
                    "DataType": "String", 
                    "StringValue": execution_id
                }
            }
            
            # Determine batch size based on number of items
            batch_size = DEFAULT_BATCH_SIZE
            if len(items_to_publish) > LARGE_BATCH_THRESHOLD:
                batch_size = LARGE_BATCH_SIZE
                logger.info(f"Using larger batch size ({LARGE_BATCH_SIZE}) for {len(items_to_publish)} items")
            
            # Use the enhanced batching functionality
            publish_result = sns_publish_data.publish_in_batches(
                topic_arn=SNS_TOPIC_ARN,
                policies=items_to_publish,
                batch_size=batch_size,
                common_attributes=common_attributes
            )
            
            results["sns_publish"] = publish_result
            
            logger.info(f"Published {publish_result.get('successful', 0)} items to SNS")
            
            if publish_result.get('failed', 0) > 0:
                logger.warning(f"Failed to publish {publish_result.get('failed', 0)} items to SNS")
        else:
            logger.info("No items to publish to SNS")
    else:
        logger.warning("SNS_TOPIC_ARN not configured - skipping publishing")
    
    return {
        "status": "success",
        "results": results,
        "execution_id": execution_id,
        "service": service
    }


def prepare_items_for_sns(results: Dict, service: str, execution_id: str) -> List[Dict]:
    """
    Prepare collected items for SNS publishing
    
    Args:
        results: Collection results
        service: Service type
        execution_id: Execution ID
        
    Returns:
        List[Dict]: Items formatted for SNS publishing
    """
    items = []
    
    for account_id, account_result in results.get("account_results", {}).items():
        if account_result.get("status") != "success":
            continue
        
        # Extract items based on service type
        if service == "IAM":
            for policy in account_result.get("policies", []):
                items.append({
                    "service": "IAM",
                    "account_id": account_id,
                    "execution_id": execution_id,
                    "resource_id": policy.get("arn"),
                    "resource_name": policy.get("name"),
                    "resource_type": "policy",
                    "data": policy
                })
        elif service == "KMS":
            for key in account_result.get("keys", []):
                items.append({
                    "service": "KMS",
                    "account_id": account_id,
                    "execution_id": execution_id,
                    "resource_id": key.get("id"),
                    "resource_name": key.get("metadata", {}).get("Description", ""),
                    "resource_type": "key",
                    "data": key
                })
        elif service == "EC2":
            for instance in account_result.get("instances", []):
                name = ""
                for tag in instance.get("tags", []):
                    if tag.get("Key") == "Name":
                        name = tag.get("Value", "")
                        break
                        
                items.append({
                    "service": "EC2",
                    "account_id": account_id,
                    "execution_id": execution_id,
                    "resource_id": instance.get("id"),
                    "resource_name": name,
                    "resource_type": "instance",
                    "data": instance
                })
        elif service == "S3":
            for bucket in account_result.get("buckets", []):
                items.append({
                    "service": "S3",
                    "account_id": account_id,
                    "execution_id": execution_id,
                    "resource_id": bucket.get("name"),
                    "resource_name": bucket.get("name"),
                    "resource_type": "bucket",
                    "data": bucket
                })
    
    return items
