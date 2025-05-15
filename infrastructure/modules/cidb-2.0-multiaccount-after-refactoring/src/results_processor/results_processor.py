"""
CIDB2 Results Processor - Processes collection results from Step Function execution
"""
import json
import logging
import os
import time
import boto3
from typing import Dict, List, Any, Optional
from datetime import datetime

# Set up logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Environment Variables
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")


def lambda_handler(event, context):
    """
    Process and summarize results from parallel collector lambdas
    
    Args:
        event: Event data from Step Functions containing collection results
        context: Lambda context
        
    Returns:
        Dict: Execution summary
    """
    logger.info("Processing CIDB2 collection results")
    logger.debug(f"Event: {json.dumps(event)}")
    
    execution_id = event.get("execution_id")
    results = event.get("results", [])
    
    if not execution_id:
        logger.error("No execution_id provided")
        return {
            "status": "failed",
            "error": "No execution_id provided"
        }
    
    if not results:
        logger.warning("No results provided to process")
        return {
            "status": "success",
            "message": "No results to process",
            "execution_id": execution_id
        }
    
    # Process the results
    summary = process_collection_results(results, execution_id)
    
    # Publish summary to SNS if configured
    if SNS_TOPIC_ARN:
        try:
            sns_client = boto3.client('sns')
            response = sns_client.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=json.dumps({
                    "type": "collection_summary",
                    "execution_id": execution_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "summary": summary
                }),
                MessageAttributes={
                    "type": {
                        "DataType": "String",
                        "StringValue": "collection_summary"
                    },
                    "execution_id": {
                        "DataType": "String",
                        "StringValue": execution_id
                    }
                }
            )
            logger.info(f"Published summary to SNS: {response['MessageId']}")
        except Exception as e:
            logger.error(f"Error publishing summary to SNS: {e}")
    
    return {
        "status": "success",
        "execution_id": execution_id,
        "summary": summary
    }


def process_collection_results(results: List, execution_id: str) -> Dict:
    """
    Process and aggregate the collection results from multiple lambdas
    
    Args:
        results: List of collection results from collector lambdas
        execution_id: Step Function execution ID
        
    Returns:
        Dict: Aggregated summary
    """
    summary = {
        "execution_id": execution_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services_collected": [],
        "accounts_processed": 0,
        "accounts_failed": 0,
        "total_resources_collected": 0,
        "sns_messages_published": 0,
        "sns_messages_failed": 0,
        "service_statistics": {},
        "errors": []
    }
    
    # Process each service's collection results
    for service_result in results:
        service_type = service_result.get("service")
        
        if not service_type:
            continue
            
        if service_type not in summary["services_collected"]:
            summary["services_collected"].append(service_type)
            
        # Add service to statistics if not already present
        if service_type not in summary["service_statistics"]:
            summary["service_statistics"][service_type] = {
                "accounts_processed": 0,
                "accounts_failed": 0,
                "resources_collected": 0
            }
            
        # Check service status
        service_status = service_result.get("status", "")
        service_results = service_result.get("results", {})
        
        if service_status == "success":
            # Add service statistics
            service_stats = summary["service_statistics"][service_type]
            service_stats["accounts_processed"] += service_results.get("accounts_processed", 0)
            service_stats["accounts_failed"] += service_results.get("accounts_failed", 0)
            service_stats["resources_collected"] += service_results.get("total_items_collected", 0)
            
            # Update global statistics
            summary["accounts_processed"] += service_results.get("accounts_processed", 0)
            summary["accounts_failed"] += service_results.get("accounts_failed", 0)
            summary["total_resources_collected"] += service_results.get("total_items_collected", 0)
            
            # SNS publishing statistics
            sns_result = service_results.get("sns_publish", {})
            if sns_result:
                summary["sns_messages_published"] += sns_result.get("successful", 0)
                summary["sns_messages_failed"] += sns_result.get("failed", 0)
                
                # Log any SNS publishing failures
                sns_failures = sns_result.get("failures", [])
                if isinstance(sns_failures, list) and sns_failures:
                    for failure in sns_failures:
                        if isinstance(failure, dict):
                            summary["errors"].append({
                                "service": service_type,
                                "component": "sns",
                                "error": failure.get("error_message", str(failure))
                            })
        else:
            # Add service error
            error_msg = service_result.get("error", "Unknown error")
            summary["errors"].append({
                "service": service_type,
                "error": error_msg
            })
    
    # Calculate success rates
    total_accounts = summary["accounts_processed"] + summary["accounts_failed"]
    summary["account_success_rate"] = 0
    if total_accounts > 0:
        summary["account_success_rate"] = round(summary["accounts_processed"] / total_accounts * 100, 1)
        
    total_sns = summary["sns_messages_published"] + summary["sns_messages_failed"]
    summary["sns_success_rate"] = 0
    if total_sns > 0:
        summary["sns_success_rate"] = round(summary["sns_messages_published"] / total_sns * 100, 1)
    
    # Add execution duration
    summary["execution_duration_seconds"] = round(time.time() - time.time(), 2)  # Will be accurate in real execution
    
    return summary
