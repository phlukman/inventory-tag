import logging
from os import environ as env
import boto3
import json
from datetime import datetime
from common_functions import generate_service_tags_inventory
from cidb2_producer import ClientSession, CIDBBase, SnsPublisher, CIDBConfig
from aws_ec2_fleet import EC2Client
from aws_cassandra_keyspaces import CassandraClient
from aws_route53_hosted_zone import Route53Client
from aws_event_rule import EventBridgeClient
from aws_process_deployment_strategy import AppConfigClient
from aws_cloud_watch_alarm import CloudWatchClient
from aws_iam_policy import IAMPolicyClient

from count_customer_policies import (
    count_customer_policies_per_account,
    split_accounts_into_slices,
    decompress_slices,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# Lambda env vars configuration
# Send messages route to: SNS->SQS->Lambda Reporter
SNS_TOPIC_ARN = env.get(
    "SNS_TOPIC_ARN",
    "arn:aws:sns:us-east-1:477591219415:dev-cidb2-lambda-collector-sns-topic",
)
# Send message warning and custom notifications
SNS_NOTIFY_ARN = env.get("SNS_NOTIFY_URL")
# Discriminate by name to execute service
FUNCTION_NAME = env.get("AWS_LAMBDA_FUNCTION_NAME")
# For local testing
EXECUTION_ENV = env.get("AWS_EXECUTION_ENV")

# Account list to query
AWS_ACCOUNT_LIST = json.loads(env.get("MEMBER_ACCOUNTS", "[]"))
# Number of array slices to split account list for aws map function concurrent processing
IAM_SLICES = int(env.get("IAM_SLICES", 6))
# Number of fixed array slices configured, equal to number of configured lambdas per group of services
FIXED_LAMBDA_N_SLICES = 2
# Region list to query
REGION_LIST = env.get("REGIONS", "us-east-1, us-east-2, us-west-2")
# Configured role in accounts
ASSUME_ROLE = env.get("ASSUME_ROLE", "EvResourceTagInventoryMemberAccountRole")
# Default deployment region
REGION = env.get("AWS_REGION", "us-east-1")
# Deployment environment
AWS_ENV = env.get("AWS_ENV", "dev")
# Bucket name to store reports
BUCKET_NAME = env.get("BUCKET_NAME", "evsharesvcnonprod-us-east-1-priv-cidb-ev-logs")

today = datetime.today()
year = today.strftime("%Y")
month = today.strftime("%B").lower()
day = today.strftime("%d")
timestamp = today.strftime("%Y%d%m")
BASE_DIR = "Custom"
# --------------------------------------------------------------
# Test data
# --------------------------------------------------------------


def process_services(event_message):

    if EXECUTION_ENV:
        # profile_name = None
        client_session = ClientSession()
    # List of selected regions
    regions = [item.strip() for item in REGION_LIST.split(",")]

    # boto3 API Configuration
    # retry_config = CIDBConfig(
    #     max_attempts=6,
    #     mode="standard"
    # )
    # Testing adaptive retry configuration
    # boto3 API Configuration with more robust retry settings
    retry_config = CIDBConfig(
        max_attempts=4,  # Reduced attempts
        mode="adaptive",  # Keep adaptive mode for throttling
        connect_timeout=5,  # Reduced connection timeout
        read_timeout=15,  # Reduced read timeout
        max_workers=3,  # Limit concurrent operations
        retries={
            "mode": "adaptive",
            "throttling": {
                "max_attempts": 6  # Still prioritize throttling retries but with limit
            },
        },
    )
    # Distribute account list in roughly equal chunks
    # Factor to split accounts into chunks. Chunks must be equal than number of dedicated lambdas
    account_split_value = FIXED_LAMBDA_N_SLICES
    k, m = divmod(len(AWS_ACCOUNT_LIST), account_split_value)
    chunk_list = [
        AWS_ACCOUNT_LIST[i * k + min(i, m) : (i + 1) * k + min(i + 1, m)]
        for i in range(account_split_value)
    ]

    client_base = CIDBBase(client_session, retry_config=retry_config)
    role_name = ASSUME_ROLE
    bucket_name = BUCKET_NAME
    # TODO: multi account services can be implemented using Dictionary Pattern Dispatch
    # Generate account configuration
    accounts_config = client_base.generate_account_config(
        accounts=chunk_list[0], regions=regions, role_name=role_name
    )
    if FUNCTION_NAME in {
        "get-events-route53_1-metadata",
        "get-cloudwatch-appconfig_1-metadata",
        "get-ec2-cassandra_1-metadata",
    }:
        accounts_config = client_base.generate_account_config(
            accounts=chunk_list[1], regions=regions, role_name=role_name
        )

    # ----------------------------------------------
    # AWS::CloudWatch::Alarm
    # ----------------------------------------------
    cloudwatch_client = CloudWatchClient(client_base)

    # ----------------------------------------------
    # AWS::AppConfig::DeploymentStrategy
    # ----------------------------------------------
    appconfig_client = AppConfigClient(client_base)

    # ----------------------------------------------
    # AWS::Events::Rule
    # ----------------------------------------------
    events_client = EventBridgeClient(client_base)

    # ----------------------------------------------
    # AWS::Route53::HostedZone
    # ----------------------------------------------
    route53_client = Route53Client(client_base)

    # ----------------------------------------------
    # "AWS::Cassandra::Keyspace" object creation
    # ----------------------------------------------
    cassandra_client = CassandraClient(client_base)

    # ----------------------------------------------
    # AWS::EC2:Fleet
    # ----------------------------------------------
    ec2_client = EC2Client(client_base)
    # ---------------------------------------------
    if FUNCTION_NAME == "get-rebalance-metadata":
        logger.info("Rebalance Lambda Function")
        # Rebalance accounts to other lambda functions
        try:
            n_slices = IAM_SLICES
            account_list = AWS_ACCOUNT_LIST
            results, policies_arns = count_customer_policies_per_account(
                account_list, role_name=role_name
            )

            # Print individual account results
            logger.info("\nCustomer IAM Policies per Account:")
            logger.info("-" * 50)
            logger.info(f"{'Account ID':<15} | {'Total Customer Policies':<20}")
            logger.info("-" * 50)

            for result in results:
                logger.info(
                    f"{result['AWSAccountID']:<15} | {result['TotalIAMCustomerPolicies']:<20}"
                )

            # Split accounts into slices with compressed ARNs
            compressed_slices = split_accounts_into_slices(
                results, policies_arns, n_slices
            )

            # For processing in this lambda, decompress the slices
            decompressed_slices = decompress_slices(compressed_slices)
            # logger.info(decompressed_slices)
            # Print slice results
            logger.info("\nSlices of Accounts:")
            logger.info(f"\nAccounts split into {len(compressed_slices)} slices:")
            logger.info("-" * 70)
            for i, slice_data in enumerate(decompressed_slices):
                logger.info(
                    f"Slice {i+1}: {slice_data['total_policies']} total policies"
                )
                logger.info(f"  Accounts: {', '.join(slice_data['accounts'].keys())}")
                logger.info("-" * 70)
            # Return slices directly for Step Functions Map
            s3 = boto3.client("s3")
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=f"{BASE_DIR}/{FUNCTION_NAME}/input.json",
                # Body=json.dumps({"slices": [{"Value": slice_data} for slice_data in compressed_slices]}),
                Body=json.dumps(
                    [{"Value": slice_data} for slice_data in compressed_slices]
                ),
            )
            # Only used from inline map function. For payloads greater than 256k use S3
            # return {
            #     "statusCode": 200,
            #     "slices": [{"Value": slice_data} for slice_data in compressed_slices],
            # }
            return {
                "statusCode": 200,
                "s3_key": f"{BASE_DIR}/{FUNCTION_NAME}/input.json",
                "bucket": BUCKET_NAME,
            }
        except Exception as e:
            logger.error(e)
            raise e

    elif FUNCTION_NAME == "get-iam-policy-metadata":
        # Handle IAM Policy collection from rebalance data
        logger.info("Processing IAM Policy collection from rebalance data")
        # logger.info(event_message)
        decompressed_slices = decompress_slices([event_message])
        logger.info("\nSlices of Accounts:")
        logger.info(f"\nAccounts split into {len(decompressed_slices)} slices:")
        logger.info("-" * 70)
        for i, slice_data in enumerate(decompressed_slices):
            logger.info(f"Slice {i+1}: {slice_data['total_policies']} total policies")
            logger.info(f"  Accounts: {', '.join(slice_data['accounts'])}")
            logger.info("-" * 70)

        iam = IAMPolicyClient(client_base, role_name)
        # -----------------------------------------------------------------------
        # SNS Test Publish
        # -----------------------------------------------------------------------
        sns_publish_data = SnsPublisher(boto3.resource("sns", region_name=REGION))
        sns_client = boto3.resource("sns", region_name=REGION)
        sns_publish_data = SnsPublisher(sns_client)
        # IAM Policy
        region = "global"
        # -----------------------------------------------------------------------------
        # Update to use map function
        # -----------------------------------------------------------------------------

        # Process policies using the new function
        # Check if decompressed_slices is a list or a single slice
        if isinstance(decompressed_slices, list):
            # If it's a list of slices, process the first slice
            if decompressed_slices:
                result = iam.list_policy_properties_from_slice(
                    decompressed_slices[0], max_workers=3
                )
                logger.info(f"Policy processing result: {result['summary']}")
            else:
                logger.error("No slice data available")
                result = {
                    "summary": {
                        "total_accounts": 0,
                        "total_policies": 0,
                        "error": "No slice data",
                    }
                }
        else:
            # If it's a single slice, process it directly
            result = iam.list_policy_properties_from_slice(
                decompressed_slices, max_workers=3
            )
            logger.info(f"Policy processing result: {result['summary']}")
        # -----------------------------------------------------------------------------
        # summary = result.get('summary', {})
        # Send Failed account to SNS Topic
        # alert_sns_msg = f"Failed accounts: {summary.get('failed_accounts', 0)}"
        # Send Policies info to SNS Topic related to SQS Queue
        common_attributes = {
            "Source": {"DataType": "String", "StringValue": "cidb2:inventory"},
            "Service": {"DataType": "String", "StringValue": "AWS::IAM::Policy"},
            "Region": {"DataType": "String", "StringValue": region},
            # "Timestamp": {"DataType": "String", "StringValue": time.strftime('%Y-%m-%dT%H:%M:%SZ')}
        }
        for account_id, account_data in result.get("accounts", {}).items():
            status = account_data.get("status", "unknown")
            if status == "success":
                # Print  policy data
                policies = account_data.get("policies", [])
                if policies:
                    # Option to save results to JSON file
                    # Send to SQS queue
                    # PERFORMANCE IMPROVEMENT: Use batch processing for SNS messages
                    # Configurable batch size - Adjust based on environment and load
                    batch_size = 10  # Default batch size

                    # For large policy sets, use larger batches
                    if len(policies) > 100:
                        batch_size = 20

                    # Call the new batching method instead of publishing messages individually
                    logger.info(
                        "Sending %d policies to SNS topic using batched publishing with batch size %d",
                        len(policies),
                        batch_size,
                    )

                    result = sns_publish_data.publish_in_batches(
                        topic_arn=SNS_TOPIC_ARN,
                        policies=policies,
                        batch_size=batch_size,
                        common_attributes=common_attributes,
                    )
                # Check results
                logger.info("Status: %s", result["status"])
                logger.info("Total messages: %s", str(result["total_messages"]))
                logger.info("Successful: %s", str(result["successful"]))
                logger.info("Failed: %s", str(result["failed"]))
        return {
            "statusCode": 200,
            "body": "IAM Policy processing completed successfully.",
        }
    elif FUNCTION_NAME in {
        "get-cloudwatch-appconfig_0-metadata",
        "get-cloudwatch-appconfig_1-metadata",
    }:
        logger.info(f"Working with accounts: {accounts_config}")
        service_type = "AWS::CloudWatch::Alarm"
        object_key = f"{BASE_DIR}/AWS-CloudWatch-Alarm/AWS-CloudWatch-Alarm-{year}-{month}-{day}-versions"
        generate_service_tags_inventory(
            cloudwatch_client, accounts_config, bucket_name, object_key, service_type
        )
        # --------------------------------------------------------
        # "AWS::AppConfig::DeploymentStrategy"
        # --------------------------------------------------------
        service_type = "AWS::AppConfig::DeploymentStrategy"
        object_key = f"{BASE_DIR}/AWS-AppConfig-DeploymentStrategy/AWS-AppConfig-DeploymentStrategy-{year}-{month}-{day}-versions"
        generate_service_tags_inventory(
            appconfig_client, accounts_config, bucket_name, object_key, service_type
        )
        return {"statusCode": 200, "body": "CWA processing completed successfully."}
    elif FUNCTION_NAME in {
        "get-events-route53_0-metadata",
        "get-events-route53_1-metadata",
    }:
        logger.info(f"Working with accounts: {accounts_config}")
        service_type = "AWS::Events::Rule"
        object_key = (
            f"{BASE_DIR}/AWS-Events-Rule/AWS-Events-Rule-{year}-{month}-{day}-versions"
        )
        generate_service_tags_inventory(
            events_client, accounts_config, bucket_name, object_key, service_type
        )
        # -------------------------------------------------------#
        # Process AWS::Route53::HostedZone
        # -------------------------------------------------------#
        service_type = "AWS::Route53::HostedZone"
        object_key = f"{BASE_DIR}/AWS-Route53-HostedZone/AWS-Route53-HostedZone-{year}-{month}-{day}-versions"
        generate_service_tags_inventory(
            route53_client, accounts_config, bucket_name, object_key, service_type
        )
        return {"statusCode": 200, "body": "EVR processing completed successfully."}

    elif FUNCTION_NAME in {
        "get-ec2-cassandra_0-metadata",
        "get-ec2-cassandra_1-metadata",
    }:
        logger.info(f"Working with accounts: {accounts_config}")
        # ----------------------------------------------
        # "AWS::EC2::Fleet"
        # ----------------------------------------------
        service_type = "AWS::EC2::Fleet"
        object_key = (
            f"{BASE_DIR}/AWS-EC2-Fleet/AWS-EC2-Fleet-{year}-{month}-{day}-versions"
        )
        generate_service_tags_inventory(
            ec2_client, accounts_config, bucket_name, object_key, service_type
        )

        # ----------------------------------------------
        # "AWS::Cassandra::Keyspace"
        # ----------------------------------------------
        service_type = "AWS::Cassandra::Keyspace"
        object_key = f"{BASE_DIR}/AWS-Cassandra-Keyspace/AWS-Cassandra-Keyspace-{year}-{month}-{day}-versions"
        generate_service_tags_inventory(
            cassandra_client, accounts_config, bucket_name, object_key, service_type
        )
        return {"statusCode": 200, "body": "EC2 processing completed successfully."}


# -------------------------------------------------------------
def lambda_handler(event, context):
    logger.info(f"Starting: {FUNCTION_NAME}")
    status = process_services(event)
    logger.info(f"{FUNCTION_NAME} Done")
    return status


if __name__ == "__main__":
    lambda_handler(None, None)
