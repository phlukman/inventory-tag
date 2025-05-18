import logging
import json
from os import environ as env
import time
import boto3
from cidb2_producer import ClientSession, CIDBBase, IAMClient, SnsPublisher, CIDBConfig
from logs import logger

logger = logging.getLogger(__name__)

ARN_TOPIC = env.get('SNS_TOPIC_ARN')
SNS_NOTIFY_ARN = env.get('SNS_NOTIFY_URL')
FUNCTION_NAME = env.get('AWS_LAMBDA_FUNCTION_NAME')
EXECUTION_ENV = env.get('AWS_EXECUTION_ENV')
ACCOUNT_LIST = env.get('ACCOUNTS')
ASSUME_ROLE =env.get('ASSUME_ROLE')
test_accounts = []
EVENT = {}
REGION = env.get('AWS_REGION')

ACCOUNT_LIST = "053210025230"
ASSUME_ROLE = "cidb-inventory-role"
ARN_TOPIC="arn:aws:sns:us-east-1:477591219415:dev-cidb2-lambda-collector-sns-topic"

if not EXECUTION_ENV:
    FUNCTION_NAME = "lambda-collector_IAM"
    ARN_TOPIC="arn:aws:sns:us-east-1:477591219415:dev-cidb2-lambda-collector-sns-topic"
    REGION = "us-east-1"

#--------------------------------------------------------------
# Test data
#--------------------------------------------------------------
test_accounts = [
    {
        "account_id": "053210025230",
        "role_name": "cidb-inventory-role",
        "region": "us-east-1"
    }
 ]
EVENT = {
        'accounts': test_accounts,
        'profile': "default"
}
#----------------------------------------------------------------
def process_services(message):
    logger.info("Received event: " + json.dumps(message, indent=2))
    # -------------------------------------------------------------
    # Config global params
    # -------------------------------------------------------------
    
    config = CIDBConfig(
        max_pool_connections=20,
        max_api_calls_per_second=10,
        max_workers=8,
        max_accounts_concurrency=5
    )


  
   
    if EXECUTION_ENV:
        profile_name = None
        accounts_list = [{"account_id": item, "role_name": ASSUME_ROLE} for item in [ACCOUNT_LIST]]
    else:
        accounts_list = EVENT.get('accounts', [])
        profile_name = EVENT.get('profile', 'default')

        # -------------------------------------------------------------
        # Initialize the client with role chaining
        # -------------------------------------------------------------
        # Step 1: Assume the CIDB2-Inventory-Role in Account A 
        # (This assumes you're already authenticated as the Engineer role or have credentials that can assume it)
        sts_client = boto3.client('sts')
        account_a_role = sts_client.assume_role(
            RoleArn="arn:aws:iam::477591219415:role/CIDB2-Inventory-Role",
            RoleSessionName="InventoryRoleSession"
        )
        # # Step 2: Create a session with Account A role credentials
        account_a_credentials = account_a_role['Credentials']
        # account_a_session = boto3.Session(
        #     aws_access_key_id=account_a_credentials['AccessKeyId'],
        #     aws_secret_access_key=account_a_credentials['SecretAccessKey'],
        #     aws_session_token=account_a_credentials['SessionToken']
        # )



    #--------------------------------------------------------------

    if FUNCTION_NAME == "dev-cidb2-collector-IAM":
        print("Initializing IAM Query")
        # Initialize the client
        if EXECUTION_ENV:
            client_session = ClientSession()
        else:
            #client_session = account_a_credentials = account_a_role['Credentials']
            client_session = boto3.Session(
                aws_access_key_id=account_a_credentials['AccessKeyId'],
                aws_secret_access_key=account_a_credentials['SecretAccessKey'],
                aws_session_token=account_a_credentials['SessionToken']
            )

            #client_session = ClientSession(profile_name=profile_name)

        client_base = CIDBBase(client_session)
        iam_client = client_base.get_client('iam', "us-east-1")
        iam = IAMClient(iam_client)
        # -----------------------------------------------------------------------
        # SNS Test Publish
        # -----------------------------------------------------------------------
        sns_publish_data = SnsPublisher(boto3.resource("sns", region_name=REGION))
        sns_client = boto3.resource('sns', region_name=REGION)
        sns_publish_data = SnsPublisher(sns_client)
        region = "global"
        # Process policies across multiple accounts
        multi_account_results = iam.list_policy_properties_multi_account(
            client_base=client_base,
            account_list=accounts_list,
            scope="Local",
            max_workers=2,          # Concurrent policy processing per account
            max_accounts_concurrency=2  # Concurrent account processing
        )
        summary = multi_account_results.get('summary', {})
        # Send Failed account to SNS Topic
        # alert_sns_msg = f"Failed accounts: {summary.get('failed_accounts', 0)}"
        # Send Policies info to SNS Topic related to SQS Queue
        #TODO: Review service in case of multi-service query
        common_attributes = {
            "Source": {"DataType": "String", "StringValue": "cidb2:inventory"},
             "Service": {"DataType": "String", "StringValue": "AWS::IAM::Policy"},
             "Region": {"DataType": "String", "StringValue": region},
            #"Timestamp": {"DataType": "String", "StringValue": time.strftime('%Y-%m-%dT%H:%M:%SZ')}
        }
        for account_id, account_data in multi_account_results.get('accounts', {}).items():
            status = account_data.get('status', 'unknown')
            if status == 'success':
                # Print  policy data
                policies = account_data.get('policies', [])
                if policies:
                    for i, policy in enumerate(policies):
                        logger.info( "Policy %s: %s",  str(i+1), policy.get('PolicyName'))
                        logger.info("ARN: %s",policy.get('PolicyArn', 'N/A'))
                        logger.info("Account ID: %s", account_id)
                        tags = policy.get('Tags', {})
                        if tags:
                            logger.debug("Tags: %s", tags)
                        else:
                            logger.debug("Tags: None")
                    # Option to save results to JSON file
                    # Send to SQS queue
                    messages = [
                        {"message": {"id": i+1, "data": policy},
                            #"attributes": {{"Service": FUNCTION_NAME}}
                            }
                        for i, policy in enumerate(policies)
                    ]
                    result = sns_publish_data.publish_batch_sns_message(
                        topic_arn= ARN_TOPIC,
                        messages= messages,
                        common_attributes=common_attributes
                        #common_attributes=None
                    )
                # Check results
                logger.info("Status: %s", result['status'])
                logger.info("Total messages: %s", str(result['total_messages']))
                logger.info("Successful: %s", str(result['successful']))
                logger.info("Failed: %s", str(result['failed']))

# -------------------------------------------------------------
def lambda_handler(event, context):
    print(FUNCTION_NAME)
    process_services(event)
    print("done")


if __name__ == "__main__":
    lambda_handler(None, None)
