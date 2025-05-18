#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Retrieve SQS queue messages 

A script for lambda to retrieve messages from SQS queue for a list of AWS services tags and generate a csv report
"""
import json
import logging
from os import environ as env
import boto3
from datetime import datetime
import csv
import re
import io
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#--------------------------------------------------------
# Construct file path
#--------------------------------------------------------
today = datetime.today()
year = today.strftime("%Y")
month = today.strftime("%B").lower()
day = today.strftime("%d")
timestamp = today.strftime("%Y%d%m")

EXECUTION_ENV = env.get('AWS_EXECUTION_ENV')
CSV_FILE = f"cidb-2.0/{year}/{month}/{month}-{day}-{timestamp}.csv"
OBJECT_KEY=f"cidb2_reporter/{CSV_FILE}"

if EXECUTION_ENV:
    BUCKET_NAME = env.get('BUCKET_NAME')
    TO_FILE = False
    REGION = env.get('AWS_REGION')
else:
    REGION = "us-east-1"
    QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/477591219415/dev-cidb2-sqs-queue"
    TO_FILE = True

BUCKET_NAME = "evsharesvcnonprod-us-east-1-priv-cidb-ev-logs"

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)   

def set_s3_client(session=None, region=None):
    """
    Set up an S3 client with the specified region and profile name

    Args:
        region (str, optional): AWS region. Defaults to None.
        profile_name (str, optional): AWS profile name. Defaults to None.

    Returns:
        boto3.client: S3 client
    """
    try:

        #session = boto3.Session(region_name=region)

        s3_client = session.client('s3', region_name=region) 
        return s3_client
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"S3 error: {error_code} - {error_message}")
        return {
            "status": "error",
            "error_code": error_code,
            "message": error_message
        }
def read_messages_from_sqs( queue_url):
    """
    Read messages from an SQS queue and process SNS topics encapsulated within them.

    Args:
        queue_url (str): The URL of the SQS queue.

    Returns:
        list: A list of processed SNS messages.
    """
    sqs_client = boto3.client('sqs', region_name=REGION)
    processed_messages = []
    service_messages = {}
    empty_queue=False
    while not empty_queue:
        try:
            # Receive messages from the SQS queue
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=2,  # Adjust as needed
                WaitTimeSeconds=20,      # Long polling
                MessageAttributeNames=['All']
            )

            logger.info("Response from SQS:%s",response)

            if 'Messages' in response:
                logger.info(f"Received {len(response['Messages'])} messages from SQS.")
                #CSV Headers
                
                for message in response['Messages']:
                    try:
                        #print(response['Messages'])
                        # Parse the SQS message body
                        body = json.loads(message['Body'])
                        aws_service = body.get('MessageAttributes', {}).get('Service', {}).get('Value', None)
                        #print(message_attributes)

                        # Check if the body contains an SNS message
                        if 'Message' in body:
                            sns_message = json.loads(body['Message'])
                            #logger.info(f"Processing SNS message: {sns_message}")
                            processed_messages.append(sns_message)
                            service_messages[aws_service]=processed_messages

                        # Delete the message from the queue after processing
                        sqs_client.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=message['ReceiptHandle']
                        )
                        logger.info(f"Deleted message from SQS: {message['MessageId']}")

                    except Exception as e:
                        logger.error(f"Error processing message: {str(e)}")
            else:
                logger.info("No messages received from SQS.")
                empty_queue = True

        except Exception as e:
            logger.error(f"Error reading messages from SQS: {str(e)}")

        #return processed_messages
        return service_messages
def read_messages_from_event(response):
    processed_messages = []
    service_messages = {}
    try:
        #print(response)
        for message in response['Records']:
            #print(message)
            try:
                # Parse the SQS message body
                body = json.loads(message['body'])
                aws_service = body.get('MessageAttributes', {}).get('Service', {}).get('Value', None)
                #print(message_attributes
                # Check if the body contains an SNS message
                if 'Message' in body:
                    sns_message = json.loads(body['Message'])
                    #logger.info(f"Processing SNS message: {sns_message}")
                    processed_messages.append(sns_message)
                    service_messages[aws_service]=processed_messages
                # Delete the message from the queue after processing
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
    except Exception as e:
        logger.info("No messages received from SQS.")
            #return processed_messages
    return service_messages

def get_awsconfig_resource_config_by_arn(account,resource_type, arn):
    try:
        #----------------------------------------------------
        # Assume Account role
        #----------------------------------------------------
        if not EXECUTION_ENV:
            logger.info("Chaining configuration")
            source_role_arn = f"arn:aws:iam::477591219415:role/CIDB2-Inventory-Role"
            source_sts_client = boto3.client('sts')
            source_account_a_role = source_sts_client.assume_role(
                RoleArn=source_role_arn,
                RoleSessionName="SourceInventoryRoleSession"
            )
            source_account_a_credentials = source_account_a_role['Credentials']
             
            target_session = boto3.Session(
                aws_access_key_id=source_account_a_credentials['AccessKeyId'],
                aws_secret_access_key=source_account_a_credentials['SecretAccessKey'],
                aws_session_token=source_account_a_credentials['SessionToken']
            )
            sts_client = target_session.client('sts')
            role_arn = f"arn:aws:iam::{account}:role/cidb-inventory-role"
            sts_client = boto3.client('sts')
            account_a_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="InventoryRoleSession"
            )
            account_a_credentials = account_a_role['Credentials']
        else:
            role_arn = f"arn:aws:iam::{account}:role/cidb-inventory-role"
            sts_client = boto3.client('sts')
            account_a_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="InventoryRoleSession"
            )

            # Step 2: Create a session with Account A role credentials
            account_a_credentials = account_a_role['Credentials']
        #----------------------------------------------------
        #session = boto3.Session()
        session = boto3.Session(
            aws_access_key_id=account_a_credentials['AccessKeyId'],
            aws_secret_access_key=account_a_credentials['SecretAccessKey'],
            aws_session_token=account_a_credentials['SessionToken']
        )
        client_conf = session.client("config", "us-east-1")

        query = f"Select resourceId WHERE resourceType = '{resource_type}' AND arn = '{str(arn)}'"
        ########print(query)
        result = client_conf.select_resource_config(
            Expression= query
        )
        #print("Result:",result)
        if len(result.get('Results', [])):
            resource_id = json.loads(result.get('Results', [])[0]).get("resourceId", {})
            awsconfig_response = client_conf.get_resource_config_history(
                resourceType = resource_type,
                resourceId = str(resource_id),
                limit = 1
            )
            #print(awsconfig_response)
            if awsconfig_response['configurationItems']:
                return awsconfig_response['configurationItems'][0]
            else:
                return None
        else:
            return None
    except Exception as e:
        logger.error("Failed to get AwsConfig ResourceId: %s", str(e))
    
def messages_to_csv(messages,awsconfig_service_name, to_file=False):
    """
    Create a CSV file with fields: Type, Arn, Tags, and AWSConfig.

    Args:
        messages (list): List of processed messages containing policy data.
    """
    arn_regex = r"^arn:aws:(?P<service>[^:]+):(?P<region>[^:]*):(?P<account_id>[^:]*):(?P<resource_name>[^:]+)\/(?P<resource>.+)$"
    csv_rows = []
    try:
        if to_file:
            with open('sqs_messages.csv', 'w', newline='') as csvfile:
                fieldnames = ['Type', 'Arn', 'Tags', 'AWSConfig']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for message in messages:
                    # Extract fields from the message
                    policy_arn = message.get('data', {}).get('PolicyArn', 'N/A')
                    policy_tags = message.get('data', {}).get('Tags', {})
                    match_values = re.match(arn_regex, policy_arn).groupdict()
                    #policy_name = f"aws:{match_values["region"]}:{match_values["service"]}:{match_values["resource_name"]}"
                    policy_name = awsconfig_service_name
                    logger.info("Service name configured: %s", awsconfig_service_name)
                    aws_config_conf = get_awsconfig_resource_config_by_arn(match_values["account_id"],resource_type=awsconfig_service_name, arn=policy_arn)  # AWSConfig data
                    # Write row to CSV
                    writer.writerow({
                        'Type': policy_name,  # Extracted from PolicyArn
                        'Arn': policy_arn,   # PolicyArn
                        'Tags': json.dumps(policy_tags),  # Tags as JSON string
                        'AWSConfig': json.dumps(aws_config_conf, cls=DateTimeEncoder) if aws_config_conf else 'N/A'  # AWSConfig data
                    })
                    csv_rows.append({
                        'Type': policy_name,  # Extracted from PolicyArn
                        'Arn': policy_arn,   # PolicyArn
                        'Tags': json.dumps(policy_tags),  # Tags as JSON string
                        'AWSConfig': json.dumps(aws_config_conf) if aws_config_conf else 'N/A'  # AWSConfig data
                    })

        
            logger.info("CSV file 'sqs_messages.csv' created successfully.")
    except Exception as e:
        #TODO: Include api config errors
        logger.error(f"CSV file creation  error: {str(e)}")
        raise
    try:
        for message in messages:
            # Extract fields from the message
            policy_arn = message.get('data', {}).get('PolicyArn', 'N/A')
            policy_tags = message.get('data', {}).get('Tags', {})
            match_values = re.match(arn_regex, policy_arn).groupdict()
            policy_name = awsconfig_service_name
            logger.info("Service name configured: %s", awsconfig_service_name)
            aws_config_conf = get_awsconfig_resource_config_by_arn(match_values["account_id"], resource_type=awsconfig_service_name, arn=policy_arn)  # AWSConfig data
            csv_rows.append({
                'Type': policy_name,  # Extracted from PolicyArn
                'Arn': policy_arn,   # PolicyArn
                'Tags': json.dumps(policy_tags),  # Tags as JSON string
                'AWSConfig': json.dumps(aws_config_conf, cls=DateTimeEncoder) if aws_config_conf else 'N/A'  # AWSConfig data
            }) 
        logger.info("CSV buffer  created successfully.")  
        return(csv_rows)
    except Exception as e:
        #TODO: Include api config errors
        logger.error(f"CSV buffer creation  error: {str(e)}")
        raise

#--------------------------------------------------------------
# CSV To S3
#--------------------------------------------------------------
def read_csv_from_s3(config_client, bucket_name, object_key):
    """
    Read a CSV file from S3

    Args:
        bucket_name (str): S3 bucket name
        object_key (str): S3 object key
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name

    Returns:
        dict: Result of the operation success, warning, error
    """
    try:

        # Get object from S3
        response = config_client.get_object(Bucket=bucket_name, Key=object_key)
        logger.info(f"File exists: s3://{bucket_name}/{object_key}")

        # Read CSV content
        csv_content = response['Body'].read().decode('utf-8')

        # Parse CSV content
        csv_reader = csv.DictReader(csv_content.splitlines())

        # Convert to list of dictionaries
        rows = list(csv_reader)

        logger.info(f"Read {len(rows)} rows from s3://{bucket_name}/{object_key}")
        return {
            "status": "success",
            "bucket": bucket_name,
            "key": object_key,
            "rows": rows
        }
    
    except config_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
             logger.warning(f"File does not exists: s3://{bucket_name}/{object_key}")
             return {
                 "status": "warning",
                "bucket": bucket_name,
                "key": object_key,
                "rows": 0
             }
        else:
            logger.error(f"S3 error: {str(e)}")
            return {
                "status": "error",
                "bucket": bucket_name,
                "key": object_key,
                "rows": 0
            }

def write_csv_to_s3(config_client ,rows, bucket_name, object_key):
    """
    Write CSV rows to S3
    
    Args:
        rows (list): List of dictionaries representing CSV rows
        bucket_name (str): S3 bucket name
        object_key (str): S3 object key
        region (str, optional): AWS region
        profile_name (str, optional): AWS profile name
        
    Returns:
        dict: Upload result
    """
    try:
        
        # Create CSV in memory
        csv_buffer = io.StringIO()
   
        if rows:
            # Get fieldnames from the first row
            fieldnames = rows[0].keys()
            if fieldnames is None:
                fieldnames = fieldnames = ['Type', 'Arn', 'Tags', 'AWSConfig']
            # Write CSV
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            
            # Upload to S3
            config_client.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=csv_buffer.getvalue(),
                ContentType='text/csv'
            )
            
            logger.info(f"Wrote {len(rows)} rows to s3://{bucket_name}/{object_key}")
            return {
                "status": "success",
                "bucket": bucket_name,
                "key": object_key,
                "count": len(rows)
            }
        else:
            logger.warning("No rows to write")
            return {
                "status": "warning",
                "message": "No rows to write"
            }           
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }



def lambda_handler(event, context):

    logger.info("Starting to process messages from SQS")
    if EXECUTION_ENV:
        logger.info("Running on Lambda")
    else:
        logger.info("Running Local")
    messages = {}
    raw_messages = {}
    current_messages = {}
    #logger.info("Raw event: %s", event)
    try:
        #print(event)
        client_session = boto3.Session()
        s3 = set_s3_client(client_session, region="us-east-1")
        # Should be created from Terraform
        #s3.create_bucket(Bucket="evsharesvcnonprod-us-east-1-priv-cidb2-test")
        if EXECUTION_ENV:
            logger.info("Read messages from lambda Events")
            raw_messages = read_messages_from_event(event)
            #print("Read csv form S3")
            #print(BUCKET_NAME, OBJECT_KEY)
            current_messages=read_csv_from_s3(s3,BUCKET_NAME,OBJECT_KEY)
            #print(current_messages)
        else:
            logger.info("Read messages directly from SQS")
            raw_messages = read_messages_from_sqs(queue_url= QUEUE_URL)
            #raw_messages = read_messages_from_event(event)
        
        #print(raw_messages)
        if len(raw_messages) == 0:
            logger.info("No messages to process")
            return {
                "status": "warning",
                "message": "No messages to process"
            }

        for awsconfig_service_name, sqs_message in raw_messages.items():
        # Extract messages from test_event
            messages = [event['message'] for event in sqs_message]
        #print("New Messages")
        #print(messages)
        
        # Write messages to CSV
        csv_rows= messages_to_csv(messages, awsconfig_service_name, to_file=TO_FILE)
        if EXECUTION_ENV:
            if current_messages["status"] == "error":
                logger.error("Failed to check S3 messages:%s",current_messages)

            elif current_messages["status"] == "success":
                csv_rows.extend(current_messages['rows'])
                #print(s3.list_objects(Bucket=BUCKET_NAME))
                write_csv_to_s3(s3,csv_rows,BUCKET_NAME,OBJECT_KEY)
            else:
                write_csv_to_s3(s3, csv_rows, BUCKET_NAME, OBJECT_KEY)
            processed_data = []
            count = 0
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise

if __name__ == '__main__':
    # Direct SNS message format
    event= {'Records': [{'messageId': '82b923c2-ce1e-4afc-a5a6-62648b06ee2a', 'receiptHandle': 'AQEBYBb9igrIKAwhWHLv2lMS7zGvAp3W2zSR+d8h/EFAt04efLvxcZc/2blLeV/ScI5MCynKpqZWlbz1ImFoHHsb/JvoXY1uuA2uPlYehA5OMM5IR8/kPRGMvYFDIbNgp47T4nArsOfqGbnjoCazEG7Qvytj3pu9APf8PnDQxjVJVMoECRqACGzzOqtJz8a0TzwlP1EjXKKlpc+qwGoijOcV+KLEquf4V2uKUzOtAr6u2M8vdrRumRRumGeeq32eTRHPMI/eiQkITw92Q8ZYFdWHVijrYQcM2oHQPbNPQHNl7HTZRxCKh3sm4E6ugve97YGzSgCby/sb7N3Lrdd5Xh3Xyx3SL8D12GWHZsTeFf9a0r9ivF8/jCHoHFIAaaPmkLhu2yF6tuVRbl1rU3Vu13+sSg==', 'body': '{\n  "Type" : "Notification",\n  "MessageId" : "26dbc29f-5865-5603-a3ae-a2029168ad0b",\n  "TopicArn" : "arn:aws:sns:us-east-1:477591219415:dev-cidb2-lambda-collector-sns-topic",\n  "Message" : "{\\"message\\": {\\"id\\": 1, \\"data\\": {\\"AccountId\\": \\"053210025230\\", \\"PolicyArn\\": \\"arn:aws:iam::053210025230:policy/KinesisFirehoseSplunk2022051914163538720000001d\\", \\"PolicyName\\": \\"KinesisFirehoseSplunk2022051914163538720000001d\\", \\"Tags\\": {\\"SOXBackup\\": \\"NA\\", \\"fin_billing_model\\": \\"dedicated\\", \\"sec_approval\\": \\"cloudsecarch-36365916\\", \\"sec_data_sensitivity\\": \\"highly_restricted\\", \\"fin_billing_environment\\": \\"labs\\", \\"inv_eon_id\\": \\"309816\\", \\"AppName\\": \\"Landing Zone\\", \\"sec_tam_environment\\": \\"dev\\", \\"obs_owning_contact\\": \\"itawscoreservices@eatonvance.com\\", \\"AppId\\": \\"lanz01\\", \\"PointOfContact\\": \\"ITAWSCoreServices@eatonvance.com\\", \\"SourceBranch\\": \\"https://github.com/Eaton-Vance-Corp/landing-zone\\", \\"DataType\\": \\"Highly Restricted\\", \\"Environment\\": \\"dev\\", \\"fin_billing_eon_id\\": \\"309816\\"}}}}",\n  "Timestamp" : "2025-05-13T22:25:17.091Z",\n  "SignatureVersion" : "1",\n  "Signature" : "sxAWItlE3jJZDbsEuRuN6TOZvjwMoswETOvhiR3n8E+ne+SkELvxBriSwDj2bYH3ARB9ZABCTsGZT/F1FZtUSKNpQJB/jZbL4aVGNwGwM9GuIVAPWSbduXUQGJuToJkCtno5uOTPT72d4LwyJV6mZilKq+WXdwVnDdiBiTc+cPFP5LYzE7R/Bp3hRfsYnuuYi6PpZOMSbgxYDiplBl8woyi8bG0GDFhx1+8+PHjLSd/WKFGOwJ7du9szkel+VCzOs/tJWzPj8vmxyEJ+EQQ3HNk66NOWvgVAlL6XAQi7CSWoXjLbXLsrkbwDuJw2fshHjsIcjPobhxbmjvUUyZ2sNg==",\n  "SigningCertURL" : "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-9c6465fa7f48f5cacd23014631ec1136.pem",\n  "UnsubscribeURL" : "https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:us-east-1:477591219415:dev-cidb2-lambda-collector-sns-topic:37f47522-29f1-4bec-92ad-eb8f5dd312ed",\n  "MessageAttributes" : {\n    "Service" : {"Type":"String","Value":"AWS::IAM::Policy"},\n    "Region" : {"Type":"String","Value":"global"},\n    "Source" : {"Type":"String","Value":"cidb2:inventory"}\n  }\n}', 'attributes': {'ApproximateReceiveCount': '1', 'SentTimestamp': '1747175117164', 'SenderId': 'AIDAIT2UOQQY3AUEKVGXU', 'ApproximateFirstReceiveTimestamp': '1747175117176'}, 'messageAttributes': {}, 'md5OfBody': '1e09c7aca8543ac59a94773e2bc6f1e1', 'eventSource': 'aws:sqs', 'eventSourceARN': 'arn:aws:sqs:us-east-1:477591219415:dev-cidb2-sqs-queue', 'awsRegion': 'us-east-1'}]}

    lambda_handler(event, None)
   
