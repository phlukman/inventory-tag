#!/usr/bin/python
"""
Save tags to SNS topic using a predefined list of AWS Services

A Script  for lambda to send a predefined services tags to a  SNS topic
"""
import logging
import os
import boto3
from datetime import datetime
logging.basicConfig(level=logging.INFO)
def fn(message):
    try:
        print(f"Processed message {(message['body'])}")
    except Exception as err:
        print(f"Error processing message: {message}")
        raise err
def lambda_handler(event, context):
    try:
        for message in event['Records']:
            fn(message)
        print("Done")
    except Exception as e:
        logging.error(e)
        raise e
if __name__ == "__main__":
    lambda_handler()