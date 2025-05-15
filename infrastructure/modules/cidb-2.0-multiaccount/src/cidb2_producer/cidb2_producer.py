"""
Purpose: AWS Resource Inventory and Tag Management
"""
import logging
import time
import threading
import concurrent.futures
from dataclasses import dataclass
import json
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from circuit_breaker import CircuitBreaker, CircuitBreakerDecorator
from logs import logger


logger = logging.getLogger(__name__)

# Common AWS error codes and their meanings
COMMON_AWS_ERRORS = {
    'AccessDenied': 'Insufficient permissions',
    'InvalidClientTokenId': 'Invalid credentials',
    'ExpiredToken': 'Credentials have expired',
    'ValidationError': 'Invalid parameters',
    'ResourceNotFoundException': 'Resource not found',
    'ThrottlingException': 'Request rate exceeded',
    'ServiceUnavailable': 'Service is temporarily unavailable',
    'NoSuchEntity': 'Entity does not exist',
    'MalformedPolicyDocument': 'Invalid policy document',
    'RequestThrottled': 'Request rate exceeded',
    'NoSessionReturned': 'Failed to get a valid session',
    'AttributeError': 'Missing attribute or method',
    'TooManyRequestsException': 'API rate limit exceeded',
    'InternalError': 'AWS internal error',
    'ConnectionError': 'Connection failed',
    'EndpointConnectionError': 'Endpoint connection failed'
}

# Error codes that should trigger circuit breaker
CIRCUIT_BREAKER_ERRORS = {
    'ThrottlingException',
    'RequestThrottled',
    'TooManyRequestsException',
    'ServiceUnavailable',
    'InternalError',
    'ConnectionError',
    'EndpointConnectionError'
}

# Helper function for extracting error details


def extract_error_code(error):
    """Extract error code and message from a ClientError"""
    if isinstance(error, ClientError):
        error_code = error.response.get('Error', {}).get('Code', 'Unknown')
        error_message = error.response.get('Error', {}).get('Message', '')
        return error_code, error_message
    return 'Unknown', str(error)


def get_error_details(error):
    """
    Extract detailed information from a ClientError exception

    Args:
        error: The exception to extract details from

    Returns:
        dict: A dictionary containing error details
    """
    if isinstance(error, ClientError):
        error_code = error.response.get('Error', {}).get('Code', 'Unknown')
        error_message = error.response.get('Error', {}).get('Message', '')
        status_code = error.response.get(
            'ResponseMetadata', {}).get('HTTPStatusCode', 0)
        request_id = error.response.get(
            'ResponseMetadata', {}).get('RequestId', '')

        # Get friendly error description if available
        error_description = COMMON_AWS_ERRORS.get(error_code, '')

        return {
            'error_code': error_code,
            'error_message': error_message,
            'status_code': status_code,
            'request_id': request_id,
            'description': error_description
        }
    return {
        'error_type': type(error).__name__,
        'error_message': str(error)
    }


@dataclass
class CIDBConfig():
    """
    CIDB configuration class

        Attributes:
        max_pool_connections (int): Maximum number of connections in the connection pool
            for AWS API clients. Higher values allow more concurrent connections but
            consume more resources. Default: 10.

        max_api_calls_per_second (int): Maximum number of AWS API calls allowed per second
            to prevent throttling. This implements rate limiting across all operations.

        max_workers (int): Maximum number of concurrent worker threads for processing
            individual resources (e.g., policies, keys) within a single account.

        max_accounts_concurrency (int): Maximum number of AWS accounts to process
            concurrently. Controls the parallelism when scanning multiple accounts.

    """
    max_pool_connections: int = 10
    max_api_calls_per_second: int = 5
    max_workers: int = 5
    max_accounts_concurrency: int = 3


class SnsPublisher:
    """Encapsulates Amazon SNS topic and subscription functions."""

    def __init__(self, sns_resource):
        """
        :param sns_resource: A Boto3 Amazon SNS resource.
        """
        self.params = CIDBConfig
        self.sns_resource = sns_resource

    def publish_sns_message(self, topic_arn, message, attributes):
        """
        Publishes a message, with attributes, to a topic. Subscriptions can be filtered
        based on message attributes so that a subscription receives messages only
        when specified attributes are present.

        :param topic_arn: The ARN of the topic to publish to.
        :param message: The message to publish.
        :param attributes: The key-value attributes to attach to the message. Values
                           must be either `str` or `bytes`.
        :return: The ID of the message.
        """
        try:
            # Get the topic object from the ARN
            topic = self.sns_resource.Topic(topic_arn)

            # Format attributes
            att_dict = {}
            for key, value in attributes.items():
                if isinstance(value, str):
                    att_dict[key] = {
                        "DataType": "String", "StringValue": value}
                elif isinstance(value, bytes):
                    att_dict[key] = {
                        "DataType": "Binary", "BinaryValue": value}

            # Convert message to JSON if it's a dict
            if isinstance(message, dict):
                message = json.dumps(message)

            # Publish the message
            response = topic.publish(
                Message=message, MessageAttributes=att_dict)
            message_id = response["MessageId"]
            logger.info(
                "Published message with attributes %s to topic %s.",
                attributes,
                topic_arn,
            )
        except ClientError:
            logger.exception(
                "Couldn't publish message to topic %s.", topic_arn)
            raise
        else:
            return message_id

    def publish_batch_sns_message(self, topic_arn, messages, common_attributes=None):
        """
        Publishes multiple messages to an SNS topic sequentially without circuit breaker or concurrency

        Args:
            topic_arn (str): The ARN of the SNS topic
            messages (list): List of messages to publish (each can be dict or str)
            common_attributes (dict, optional): Common message attributes for all messages

        Returns:
            dict: Summary of the operation including success/failure counts
        """

        if not messages:
            logger.warning("Empty messages list provided, nothing to send")
            return {
                'status': 'completed',
                'total_messages': 0,
                'successful': 0,
                'failed': 0,
                'results': []
            }

        total_messages = len(messages)
        logger.info("Sending %d messages to SNS topic %s",
                    total_messages, topic_arn)

        # Get the topic
        topic = self.sns_resource.Topic(topic_arn)

        # Initialize counters and results
        successful_count = 0
        failed_count = 0
        results = []

        # Process each message sequentially
        for index, message in enumerate(messages):
            try:
                # Extract message-specific attributes if available
                message_attributes = common_attributes.copy() if common_attributes else {}

                if isinstance(message, dict) and 'attributes' in message:
                    # Format attributes for SNS
                    for key, value in message['attributes'].items():
                        if isinstance(value, str):
                            message_attributes[key] = {
                                "DataType": "String", "StringValue": value}
                        elif isinstance(value, bytes):
                            message_attributes[key] = {
                                "DataType": "Binary", "BinaryValue": value}

                    # Use the actual message content
                    actual_message = message.get('message', message)
                else:
                    actual_message = message

                # Convert message to string if it's a dict
                if isinstance(actual_message, dict):
                    actual_message = json.dumps(actual_message)

                # Publish the message
                response = topic.publish(
                    Message=actual_message, MessageAttributes=message_attributes)
                message_id = response.get("MessageId")

                # Record success
                successful_count += 1
                results.append({
                    'index': index,
                    'status': 'success',
                    'MessageId': message_id
                })

                logger.debug("Published message %d to topic %s",
                            index, topic_arn)

            except Exception as e:
                # Record failure
                failed_count += 1
                results.append({
                    'index': index,
                    'status': 'failed',
                    'error': str(e)
                })

                logger.error("Failed to publish message %d to topic %s: %s",
                             index, topic_arn, str(e))

        # Prepare summary
        summary = {
            'status': 'completed',
            'total_messages': total_messages,
            'successful': successful_count,
            'failed': failed_count,
            'results': results
        }

        logger.info("Completed sending to SNS. Success: %d/%d, Failed: %d/%d",
                    successful_count, total_messages, failed_count, total_messages)

        return summary


class ClientSession:
    """
    A client session that can be used to create clients with a specific profile.
    """

    def __init__(self, profile_name=None):
        self.profile_name = profile_name
        self.params = CIDBConfig


    def get_session(self):
        try:
            return boto3.Session(profile_name=self.profile_name)
        except ClientError as e:
            error_code, _ = extract_error_code(e)
            logger.error("Failed to create session: %s", error_code)
            raise


class CIDBBase:
    """ 
    Base class for all clients
    """

    def __init__(self, client_session: ClientSession, retry_config=None):
        self.params = CIDBConfig
        self.client_session = client_session
        self.retry_config = retry_config or Config(
            retries={
                'max_attempts': 3,
                'mode': 'standard'
            }
        )
        # Dictionary to store AWS clients with circuit breakers
        self._aws_clients = {}

    def get_client(self, service_name, region_name=None):
        """
        Get an AWS client with circuit breaker protection

        Args:
            service_name (str): The AWS service name (e.g., 'ec2', 's3')
            region_name (str, optional): The AWS region name

        Returns:
            AWSClient: A client for the specified service with circuit breaker protection
        """
        # Create a unique key for this client
        client_key = f"{service_name}-{region_name or 'default'}"

        # Return existing client if we have one
        if client_key in self._aws_clients:
            return self._aws_clients[client_key]

        try:
            # Get the boto3 session
            if hasattr(self.client_session, 'client'):
                # It's already a boto3.Session object
                boto3_session = self.client_session
            else:
                # It's our ClientSession class, so get the boto3.Session first
                boto3_session = self.client_session.get_session()

            return boto3_session.client(service_name, region_name=region_name)

        except ClientError as err:
            error_code, _ = extract_error_code(err)
            logger.error("Failed to get %s client: %s",
                         service_name, error_code)
            raise
        except Exception as e:
            logger.error("Unexpected error creating %s client: %s",
                         service_name, type(e).__name__)
            raise

    def assume_role(self, account_id, role_name):
        """
        Assume a role in the specified account

        Args:
            account_id (str): The AWS account ID
            role_name (str): The name of the role to assume

        Returns:
            boto3.Session: A session with the assumed role credentials

        Raises:
            ClientError: If there's an error assuming the role
        """
        try:
            # Get the STS client
            sts_client = self.get_client('sts')
        except ClientError as err:
            error_code, _ = extract_error_code(err)
            logger.error("Failed to create STS client: %s", error_code)
            raise

        # Construct the full role ARN
        full_role_name = f'arn:aws:iam::{account_id}:role/{role_name}'

        try:
            logger.info("Assuming role in account %s", account_id)
            response = sts_client.assume_role(
                RoleArn=full_role_name,
                RoleSessionName='AWSAutoInventorySession',
                DurationSeconds=3600
            )
        except ClientError as err:
            error_code, error_message = extract_error_code(err)

            if error_code == 'AccessDenied':
                logger.error(
                    "Access denied for role %s in account %s", role_name, account_id)
            elif error_code == 'InvalidClientTokenId':
                logger.error("Invalid credentials for account %s", account_id)
            else:
                logger.error(
                    "Failed to assume role in account %s: %s", account_id, error_code)

            raise

        try:
            credentials = response['Credentials']
            logger.info("Successfully assumed role in account %s", account_id)
            return boto3.Session(
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        except KeyError:
            logger.error(
                "Missing credentials in response for account %s", account_id)
            return None
        except Exception as err:
            logger.error("Failed to create session for account %s: %s",
                         account_id, type(err).__name__)
            return None


class IAMClient:
    def __init__(self, client: CIDBBase):
        self.client = client
        self.params = CIDBConfig

    def list_policy_properties_multi_account(self, client_base, account_list, scope="All", max_workers=5, max_accounts_concurrency=3):
        """
        List IAM policies with their properties across multiple AWS accounts

        Args:
            client_base (CIDBBase): The base client for AWS operations
            account_list (list): List of account dictionaries with account_id and role_name
            scope (str): The scope of policies to list ('All', 'AWS', or 'Local')
            max_workers (int): Maximum number of concurrent workers for tag retrieval
            max_accounts_concurrency (int): Maximum number of accounts to process concurrently

        Returns:
            dict: A dictionary containing policies and statistics by account
        """
        statistics = {
                        'total': 0,
                        'tagged': 0,
                        'untagged': 0,
                        'tagging_percentage': 0
                     }
        try:
            # Create circuit breakers
            assume_role_cb = CircuitBreaker(
                name="assume-role", failure_threshold=3, recovery_timeout=60)
            list_cb = CircuitBreaker(
                name="iam-list-policies", failure_threshold=3, recovery_timeout=30)
            tag_cb = CircuitBreaker(
                name="iam-policy-tags", failure_threshold=5, recovery_timeout=15)
            # Thread-safe counter for API calls
            # api_call_counter = {'count': 0}
            # api_call_lock = threading.Lock()
            # # Maximum API calls per second (to avoid throttling)
            # MAX_API_CALLS_PER_SECOND = self.params.max_api_calls_per_second
            # last_api_call_time = {'time': time.time()}
            # 
            # def rate_limit_api_call():
            #     """Apply rate limiting to API calls"""
            #     with api_call_lock:
            #         current_time = time.time()
            #         time_since_last_call = current_time - \
            #             last_api_call_time['time']
            #         # If we're making too many calls per second, sleep
            #         if api_call_counter['count'] >= MAX_API_CALLS_PER_SECOND and time_since_last_call < 1.0:
            #             sleep_time = 1.0 - time_since_last_call
            #             time.sleep(sleep_time)
            #             last_api_call_time['time'] = time.time()
            #             api_call_counter['count'] = 0
            #         elif time_since_last_call >= 1.0:
            #             # Reset counter if more than a second has passed
            #             last_api_call_time['time'] = current_time
            #             api_call_counter['count'] = 0
            #         # Increment the counter
            #         api_call_counter['count'] += 1
            # Define fallback functions

            def assume_role_fallback(account_info):
                logger.warning("Using fallback for assume role: %s",
                               account_info.get('account_id'))
                return None

            def list_policies_fallback():
                logger.warning("Using fallback for list policies")
                return {'Policies': []}

            def tag_fallback(policy_arn):
                logger.warning(
                    "Using fallback for policy tags: %s", policy_arn)
                return {}
            # Create decorators with circuit breakers
            assume_role_decorator = CircuitBreakerDecorator(
                assume_role_cb, assume_role_fallback)
            list_policies_decorator = CircuitBreakerDecorator(
                list_cb, list_policies_fallback)
            tag_decorator = CircuitBreakerDecorator(tag_cb, tag_fallback)

            # Decorate the assume role function
            @assume_role_decorator
            def assume_role_with_cb(account_info):
                account_id = account_info.get('account_id')
                role_name = account_info.get('role_name')
                # Apply rate limiting
                #rate_limit_api_call()
                try:
                    # Assume role in the target account
                    assumed_session = client_base.assume_role(
                        account_id, role_name)
                    if not assumed_session:
                        logger.error(
                            "Failed to assume role in account %s", account_id)
                        return None
                    # Get account identity for verification
                    assumed_account_id = assumed_session.client(
                        'sts').get_caller_identity()
                    logger.info(
                        "Successfully assumed role in account %s", account_id)
                    return {
                        'session': assumed_session,
                        'identity': assumed_account_id
                    }
                except Exception as e:
                    logger.error(
                        "Error assuming role for account %s: %s", account_id, str(e))
                    assume_role_cb.record_failure(e)
                    return None
            # Decorate the list policies function

            @list_policies_decorator
            def list_policies_with_cb(iam_client, scope):
                # Apply rate limiting
                #rate_limit_api_call()
                return iam_client.list_policies(
                    Scope=scope,
                )
            # Decorate the tag retrieval function

            @tag_decorator
            def get_policy_tags_with_cb(iam_client, policy_arn):
                try:
                    # Apply rate limiting
                    #rate_limit_api_call()
                    response = iam_client.list_policy_tags(
                        PolicyArn=policy_arn)
                    tags = response.get('Tags', [])
                    # Convert tags to a more usable format
                    formatted_tags = {}
                    for tag in tags:
                        if 'Key' in tag and 'Value' in tag:
                            formatted_tags[tag['Key']] = tag['Value']

                    return formatted_tags
                except ClientError as err:
                    logger.warning(
                        "Failed to get tags for policy %s : %s", account_id, str(err))
                    tag_cb.record_failure(err)
                    return {}

            # Function to process a single policy
            def process_policy(iam_client, policy, account_id):
                policy_arn = policy['Arn']
                policy_name = policy.get('PolicyName', '')

                # Extract basic policy properties
                policy_properties = {
                    'AccountId': account_id,
                    'PolicyArn': policy_arn,
                    'PolicyName': policy_name
                }

                # Get policy tags with circuit breaker protection
                tags = get_policy_tags_with_cb(iam_client, policy_arn)

                # Add tags to policy properties
                policy_properties['Tags'] = tags

                # Record success in the circuit breaker
                tag_cb.record_success()

                return policy_properties

            # Function to process a single account
            def process_account(account_info):
                account_id = account_info.get('account_id')
               
                try:
                    # Check if circuit breaker allows the request
                    if not assume_role_cb.allow_request():
                        logger.warning(
                            "Circuit breaker is OPEN for assume role, skipping account %s", account_id)
                        return {
                            'account_id': account_id,
                            'status': 'circuit_open',
                            'policies': [],
                            'statistics': statistics
                        }

                    # Assume role with circuit breaker protection
                    assumed_role = assume_role_with_cb(account_info)
                    if not assumed_role:
                        return {
                            'account_id': account_id,
                            'status': 'failed',
                            'error': 'Failed to assume role',
                            'policies': [],
                            'statistics': statistics
                        }

                    assumed_session = assumed_role['session']
                    identity = assumed_role['identity']

                    # Create IAM client
                    iam_client = assumed_session.client('iam')

                    # Check if circuit breaker allows the request
                    if not list_cb.allow_request():
                        logger.warning(
                            "Circuit breaker is OPEN for list policies, skipping account %s", account_id)
                        return {
                            'account_id': account_id,
                            'status': 'circuit_open',
                            'policies': [],
                            'statistics': statistics
                        }

                    # List policies with circuit breaker protection
                    response = list_policies_with_cb(iam_client, scope)
                    policy_list = response.get('Policies', [])

                    # Record success in the circuit breaker
                    list_cb.record_success()

                    # Process policies and their tags concurrently
                    policies = []

                    # Use ThreadPoolExecutor for concurrent processing of policies
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                        # Submit all tasks
                        future_to_policy = {
                            executor.submit(process_policy, iam_client, policy, account_id): policy
                            for policy in policy_list
                        }

                        # Process results as they complete
                        for future in concurrent.futures.as_completed(future_to_policy):
                            try:
                                policy_properties = future.result()
                                policies.append(policy_properties)
                            except Exception as e:
                                policy = future_to_policy[future]
                                logger.error("Error processing policy %s in account %s: %s",
                                             policy.get('Arn', 'unknown'), account_id, str(e))

                    # Calculate tag statistics
                    tagged_count = sum(1 for p in policies if p.get('Tags'))
                    untagged_count = len(policies) - tagged_count

                    logger.info("Account %s: Retrieved %d policies (%d tagged, %d untagged)",
                                account_id, len(policies), tagged_count, untagged_count)

                    # Record success in the circuit breaker
                    assume_role_cb.record_success()

                    return {
                        'account_id': account_id,
                        'status': 'success',
                        'identity': identity,
                        'policies': policies,
                        'statistics': {
                            'total': len(policies),
                            'tagged': tagged_count,
                            'untagged': untagged_count,
                            'tagging_percentage': (tagged_count / len(policies) * 100) if policies else 0
                        }
                    }

                except Exception as e:
                    logger.error("Error processing account %s: %s",
                                 account_id, str(e))
                    return {
                        'account_id': account_id,
                        'status': 'failed',
                        'error': str(e),
                        'policies': [],
                        'statistics': statistics
                        }
            # # Process all accounts concurrently
            start_time = time.time()
            results = {
                'accounts': {},
                'all_policies': [],
                'execution_time': {
                    'start': start_time,
                    'end': None,
                    'duration_seconds': None
                }
            }

            logger.info("Processing %d accounts with max concurrency %d",
                        len(account_list), max_accounts_concurrency)

            # Use ThreadPoolExecutor for concurrent processing of accounts
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_accounts_concurrency) as executor:
                # Submit all tasks
                future_to_account = {
                    executor.submit(process_account, account_info): account_info.get('account_id')
                    for account_info in account_list
                }

                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_account):
                    account_id = future_to_account[future]
                    try:
                        account_result = future.result()
                        results['accounts'][account_id] = account_result

                        # Add policies to the combined list
                        if account_result.get('status') == 'success':
                            results['all_policies'].extend(
                                account_result.get('policies', []))

                    except Exception as e:
                        logger.error(
                            "Error processing future for account %s: %s", account_id, str(e))
                        results['accounts'][account_id] = {
                            'account_id': account_id,
                            'status': 'failed',
                            'error': str(e),
                            'policies': [],
                        }
                        results['accounts'][account_id]['statistics'] = statistics
            # # Calculate overall statistics
            successful_accounts = sum(
                1 for acc in results['accounts'].values() if acc.get('status') == 'success')
            failed_accounts = sum(
                1 for acc in results['accounts'].values() if acc.get('status') == 'failed')
            circuit_open_accounts = sum(
                1 for acc in results['accounts'].values() if acc.get('status') == 'circuit_open')

            total_policies = len(results['all_policies'])
            tagged_policies = sum(
                1 for p in results['all_policies'] if p.get('Tags'))
            untagged_policies = total_policies - tagged_policies

            # Add execution time information
            end_time = time.time()
            results['execution_time']['end'] = end_time
            results['execution_time']['duration_seconds'] = end_time - start_time

            # Add summary to results
            results['summary'] = {
                'total_accounts': len(account_list),
                'successful_accounts': successful_accounts,
                'failed_accounts': failed_accounts,
                'circuit_open_accounts': circuit_open_accounts,
                'total_policies': total_policies,
                'tagged_policies': tagged_policies,
                'untagged_policies': untagged_policies,
                'tagging_percentage': (tagged_policies / total_policies * 100) if total_policies > 0 else 0,
                'execution_time_seconds': results['execution_time']['duration_seconds']
            }

            # Add circuit breaker states
            results['circuit_breaker_states'] = {
                'assume_role': assume_role_cb.get_state(),
                'list_policies': list_cb.get_state(),
                'policy_tags': tag_cb.get_state()
            }

            logger.info("Completed processing %d accounts in %.2f seconds",
                        len(account_list), results['execution_time']['duration_seconds'])
            logger.info("Found %d policies across %d accounts (%d tagged, %d untagged)",
                        total_policies, successful_accounts, tagged_policies, untagged_policies)

            return results

        except Exception as e:
            logger.error(
                "Unexpected error in list_policy_properties_multi_account: %s", str(e))
            return {
                'accounts': {},
                'all_policies': [],
                'summary': {
                    'total_accounts': len(account_list),
                    'successful_accounts': 0,
                    'failed_accounts': len(account_list),
                    'circuit_open_accounts': 0,
                    'total_policies': 0,
                    'tagged_policies': 0,
                    'untagged_policies': 0,
                    'tagging_percentage': 0
                },
                'error': {
                    'type': type(e).__name__,
                    'message': str(e)
                }
            }


class KMSClient:
    def __init__(self, client: CIDBBase):
        self.client = client
