#!/usr/bin/python
"""
Save tags to SNS topicusing a predefined lists os AWS Services

A Script  for lambda to send a predefind services tags to a  SNS topic
"""
import logging
import os
import boto3
logging.basicConfig(level=logging.INFO)
def fn():
    client = boto3.client('sns')
    myTopicArn = os.environ['SNS_TOPIC_ARN']
    lambdaName = os.environ['AWS_LAMBDA_FUNCTION_NAME']
    response = client.publish(TopicArn=str(myTopicArn),Message=f'Message from lambda: {lambdaName}')
    return(response)
def lambda_handler(event, context):
    try:
       return fn()
    except Exception as e:
        logging.error(e)
        raise e
if __name__ == 'main':
    lambda_handler()