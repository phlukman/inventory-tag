"""
CIDB2 Producer - Multi-account AWS inventory collection
"""
import json
import logging
import os
import boto3
import time
import math
from botocore.exceptions import ClientError
from typing import Dict, List, Any, Optional, Union, Tuple

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

class SnsPublisher:
    """
    Responsible for publishing messages to SNS topics
    Enhanced with batch processing capabilities
    """
    def __init__(self, session=None):
        """
        Initialize SNS client with the provided session or default
        """
        if session:
            self.sns_client = session.client('sns')
        else:
            self.sns_client = boto3.client('sns')

    def publish_message(self, topic_arn: str, message: Dict, attributes: Optional[Dict] = None) -> Dict:
        """
        Publish a single message to an SNS topic
        
        Args:
            topic_arn: ARN of the SNS topic
            message: Message to publish
            attributes: Message attributes
            
        Returns:
            Dict: Response from SNS
        """
        try:
            if attributes:
                response = self.sns_client.publish(
                    TopicArn=topic_arn,
                    Message=json.dumps(message),
                    MessageAttributes=attributes
                )
            else:
                response = self.sns_client.publish(
                    TopicArn=topic_arn,
                    Message=json.dumps(message)
                )
            return response
        except ClientError as e:
            logger.error(f"Error publishing message to SNS: {e}")
            raise

    def publish_batch_sns_message(self, topic_arn: str, messages: List[Dict], 
                                common_attributes: Optional[Dict] = None) -> Dict:
        """
        Publish multiple messages to an SNS topic individually
        
        Args:
            topic_arn: ARN of the SNS topic
            messages: List of messages to publish
            common_attributes: Message attributes to apply to all messages
            
        Returns:
            Dict: Summary of published messages
        """
        successes = []
        failures = []
        
        for message in messages:
            try:
                response = self.publish_message(topic_arn, message, common_attributes)
                successes.append({
                    "message_id": response['MessageId'],
                    "status": "success"
                })
            except Exception as e:
                failures.append({
                    "error": str(e),
                    "status": "failed"
                })
                
        return {
            "successful": len(successes),
            "failed": len(failures),
            "successes": successes,
            "failures": failures
        }

    def publish_in_batches(self, topic_arn: str, policies: List[Dict], 
                          batch_size: int = 10, common_attributes: Optional[Dict] = None) -> Dict:
        """
        Efficiently publishes multiple messages to an SNS topic using batching
        
        Args:
            topic_arn: ARN of the SNS topic
            policies: List of policy messages to publish
            batch_size: Number of messages per batch (default: 10)
            common_attributes: Message attributes to apply to all messages
            
        Returns:
            Dict: Summary of the batch publishing operation
        """
        start_time = time.time()
        
        # Calculate total number of batches
        total_messages = len(policies)
        total_batches = math.ceil(total_messages / batch_size)
        
        logger.info(f"Publishing {total_messages} messages to SNS topic in {total_batches} batches")
        
        successes = []
        failures = []
        
        # Process messages in batches
        for batch_index in range(total_batches):
            batch_start = batch_index * batch_size
            batch_end = min((batch_index + 1) * batch_size, total_messages)
            batch = policies[batch_start:batch_end]
            
            batch_start_time = time.time()
            logger.info(f"Processing batch {batch_index + 1}/{total_batches} ({len(batch)} messages)")
            
            # Process each message in the batch
            for message in batch:
                try:
                    response = self.publish_message(topic_arn, message, common_attributes)
                    successes.append({
                        "message_id": response['MessageId'],
                        "status": "success"
                    })
                except ClientError as e:
                    error_code = e.response['Error']['Code'] if 'Error' in e.response else 'Unknown'
                    error_msg = e.response['Error']['Message'] if 'Error' in e.response else str(e)
                    
                    failures.append({
                        "error_code": error_code,
                        "error_message": error_msg,
                        "status": "failed"
                    })
                    
                    # Log detailed error information
                    logger.error(f"Error publishing message to SNS: {error_code} - {error_msg}")
                except Exception as e:
                    failures.append({
                        "error": str(e),
                        "status": "failed"
                    })
                    logger.error(f"Unexpected error publishing message to SNS: {e}")
            
            # Calculate and log batch metrics
            batch_duration = time.time() - batch_start_time
            logger.info(f"Batch {batch_index + 1} completed in {batch_duration:.2f}s " +
                        f"({len(batch)/(batch_duration or 1):.1f} messages/sec)")
            
            # Add a small delay between batches to prevent throttling
            if batch_index < total_batches - 1:
                time.sleep(0.2)
        
        # Calculate overall metrics
        total_duration = time.time() - start_time
        success_rate = len(successes) / total_messages * 100 if total_messages > 0 else 0
        
        result = {
            "total_messages": total_messages,
            "successful": len(successes),
            "failed": len(failures),
            "success_rate": f"{success_rate:.1f}%",
            "duration_seconds": f"{total_duration:.2f}",
            "messages_per_second": f"{total_messages/(total_duration or 1):.1f}",
            "successes": successes[:10] if len(successes) <= 10 else f"{len(successes)} successes",
            "failures": failures if failures else "No failures"
        }
        
        logger.info(f"SNS batch publishing completed: {result['successful']}/{total_messages} " +
                   f"messages published successfully ({result['success_rate']})")
        
        if failures:
            logger.warning(f"Failed to publish {len(failures)} messages to SNS")
        
        return result


class AwsAccountCollector:
    """
    Base class for collecting data from AWS accounts
    """
    def __init__(self, role_name: str, region: str = "us-east-1"):
        """
        Initialize with the role to assume and region
        """
        self.role_name = role_name
        self.region = region
        self.session = boto3.Session(region_name=region)
        self.sns_publisher = SnsPublisher(self.session)
    
    def assume_role(self, account_id: str) -> boto3.Session:
        """
        Assume the specified role in the target account
        
        Args:
            account_id: Target AWS account ID
            
        Returns:
            boto3.Session: Session with the assumed role
        """
        role_arn = f"arn:aws:iam::{account_id}:role/{self.role_name}"
        
        try:
            sts_client = self.session.client('sts')
            response = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="CIDB2-Collection"
            )
            
            # Create a session with the temporary credentials
            return boto3.Session(
                aws_access_key_id=response['Credentials']['AccessKeyId'],
                aws_secret_access_key=response['Credentials']['SecretAccessKey'],
                aws_session_token=response['Credentials']['SessionToken'],
                region_name=self.region
            )
        except ClientError as e:
            logger.error(f"Failed to assume role {role_arn}: {e}")
            raise

    def collect_from_accounts(self, accounts: List[str], service_type: str) -> Dict:
        """
        Collect data from multiple AWS accounts
        
        Args:
            accounts: List of AWS account IDs
            service_type: Type of AWS service to collect data from
            
        Returns:
            Dict: Collection results
        """
        results = {
            "service": service_type,
            "accounts_processed": 0,
            "accounts_failed": 0,
            "total_items_collected": 0,
            "account_results": {}
        }
        
        for account_id in accounts:
            try:
                logger.info(f"Collecting {service_type} data from account {account_id}")
                
                # Assume role in the target account
                session = self.assume_role(account_id)
                
                # Collect data using the appropriate collector
                if service_type == "IAM":
                    collector = IamPolicyCollector(session)
                    account_result = collector.collect_policies()
                elif service_type == "KMS":
                    collector = KmsKeyCollector(session)
                    account_result = collector.collect_keys()
                elif service_type == "EC2":
                    collector = Ec2InstanceCollector(session)
                    account_result = collector.collect_instances()
                elif service_type == "S3":
                    collector = S3BucketCollector(session)
                    account_result = collector.collect_buckets()
                else:
                    logger.error(f"Unsupported service type: {service_type}")
                    raise ValueError(f"Unsupported service type: {service_type}")
                
                # Update results
                results["accounts_processed"] += 1
                results["total_items_collected"] += account_result.get("items_collected", 0)
                results["account_results"][account_id] = account_result
                
            except Exception as e:
                logger.error(f"Error collecting from account {account_id}: {e}")
                results["accounts_failed"] += 1
                results["account_results"][account_id] = {
                    "status": "failed",
                    "error": str(e)
                }
        
        return results


class IamPolicyCollector:
    """Collects IAM policies from an AWS account"""
    
    def __init__(self, session):
        self.session = session
        self.iam_client = session.client('iam')
        
    def collect_policies(self) -> Dict:
        """
        Collect IAM policies
        
        Returns:
            Dict: Collection results
        """
        try:
            # Get all managed policies
            paginator = self.iam_client.get_paginator('list_policies')
            policies = []
            
            for page in paginator.paginate(Scope='Local'):
                for policy in page['Policies']:
                    policy_detail = self.iam_client.get_policy(
                        PolicyArn=policy['Arn']
                    )['Policy']
                    
                    # Get the policy document
                    policy_version = self.iam_client.get_policy_version(
                        PolicyArn=policy['Arn'],
                        VersionId=policy_detail['DefaultVersionId']
                    )
                    
                    policies.append({
                        'arn': policy['Arn'],
                        'name': policy['PolicyName'],
                        'description': policy.get('Description', ''),
                        'document': policy_version['PolicyVersion']['Document']
                    })
            
            return {
                "status": "success",
                "items_collected": len(policies),
                "policies": policies
            }
        except Exception as e:
            logger.error(f"Error collecting IAM policies: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }


class KmsKeyCollector:
    """Collects KMS keys from an AWS account"""
    
    def __init__(self, session):
        self.session = session
        self.kms_client = session.client('kms')
        
    def collect_keys(self) -> Dict:
        """
        Collect KMS keys
        
        Returns:
            Dict: Collection results
        """
        try:
            keys = []
            paginator = self.kms_client.get_paginator('list_keys')
            
            for page in paginator.paginate():
                for key in page['Keys']:
                    try:
                        # Get key details
                        key_detail = self.kms_client.describe_key(
                            KeyId=key['KeyId']
                        )['KeyMetadata']
                        
                        # Skip AWS managed keys
                        if key_detail.get('KeyManager') == 'AWS':
                            continue
                        
                        # Get key policy
                        policy = self.kms_client.get_key_policy(
                            KeyId=key['KeyId'],
                            PolicyName='default'
                        )['Policy']
                        
                        keys.append({
                            'id': key['KeyId'],
                            'arn': key['KeyArn'],
                            'metadata': key_detail,
                            'policy': json.loads(policy) if isinstance(policy, str) else policy
                        })
                    except ClientError:
                        # Skip keys we can't access
                        continue
            
            return {
                "status": "success",
                "items_collected": len(keys),
                "keys": keys
            }
        except Exception as e:
            logger.error(f"Error collecting KMS keys: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }


class Ec2InstanceCollector:
    """Collects EC2 instances from an AWS account"""
    
    def __init__(self, session):
        self.session = session
        self.ec2_client = session.client('ec2')
        
    def collect_instances(self) -> Dict:
        """
        Collect EC2 instances
        
        Returns:
            Dict: Collection results
        """
        try:
            instances = []
            paginator = self.ec2_client.get_paginator('describe_instances')
            
            for page in paginator.paginate():
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        instances.append({
                            'id': instance['InstanceId'],
                            'type': instance['InstanceType'],
                            'state': instance['State']['Name'],
                            'tags': instance.get('Tags', []),
                            'launch_time': instance.get('LaunchTime', '').isoformat() if 'LaunchTime' in instance else '',
                            'vpc_id': instance.get('VpcId', '')
                        })
            
            return {
                "status": "success",
                "items_collected": len(instances),
                "instances": instances
            }
        except Exception as e:
            logger.error(f"Error collecting EC2 instances: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }


class S3BucketCollector:
    """Collects S3 buckets from an AWS account"""
    
    def __init__(self, session):
        self.session = session
        self.s3_client = session.client('s3')
        
    def collect_buckets(self) -> Dict:
        """
        Collect S3 buckets and their policies
        
        Returns:
            Dict: Collection results
        """
        try:
            buckets = []
            response = self.s3_client.list_buckets()
            
            for bucket in response['Buckets']:
                bucket_info = {
                    'name': bucket['Name'],
                    'creation_date': bucket['CreationDate'].isoformat() if 'CreationDate' in bucket else '',
                }
                
                try:
                    # Get bucket policy
                    policy_response = self.s3_client.get_bucket_policy(Bucket=bucket['Name'])
                    bucket_info['policy'] = json.loads(policy_response['Policy'])
                except ClientError as e:
                    if e.response['Error']['Code'] == 'NoSuchBucketPolicy':
                        bucket_info['policy'] = None
                    else:
                        # Skip buckets we can't access
                        continue
                
                buckets.append(bucket_info)
            
            return {
                "status": "success",
                "items_collected": len(buckets),
                "buckets": buckets
            }
        except Exception as e:
            logger.error(f"Error collecting S3 buckets: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
