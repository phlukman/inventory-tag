"""
Purpose: AWS Resource Inventory and Tag Management
"""

import logging
import time
from dataclasses import dataclass, field
import json
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
import math

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# Common AWS error codes and their meanings
COMMON_AWS_ERRORS = {
    "AccessDenied": "Insufficient permissions",
    "InvalidClientTokenId": "Invalid credentials",
    "ExpiredToken": "Credentials have expired",
    "ValidationError": "Invalid parameters",
    "ResourceNotFoundException": "Resource not found",
    "ThrottlingException": "Request rate exceeded",
    "ServiceUnavailable": "Service is temporarily unavailable",
    "NoSuchEntity": "Entity does not exist",
    "MalformedPolicyDocument": "Invalid policy document",
    "RequestThrottled": "Request rate exceeded",
    "NoSessionReturned": "Failed to get a valid session",
    "AttributeError": "Missing attribute or method",
    "TooManyRequestsException": "API rate limit exceeded",
    "InternalError": "AWS internal error",
    "ConnectionError": "Connection failed",
    "EndpointConnectionError": "Endpoint connection failed",
}

# # Error codes that should trigger circuit breaker
CIRCUIT_BREAKER_ERRORS = {
    "ThrottlingException",
    "RequestThrottled",
    "TooManyRequestsException",
    "ServiceUnavailable",
    "InternalError",
    "ConnectionError",
    "EndpointConnectionError",
}

# Helper function for extracting error details


def extract_error_code(error):
    """Extract error code and message from a ClientError"""
    if isinstance(error, ClientError):
        error_code = error.response.get("Error", {}).get("Code", "Unknown")
        error_message = error.response.get("Error", {}).get("Message", "")
        return error_code, error_message
    return "Unknown", str(error)


def get_error_details(error):
    """
    Extract detailed information from a ClientError exception

    Args:
        error: The exception to extract details from

    Returns:
        dict: A dictionary containing error details
    """
    if isinstance(error, ClientError):
        error_code = error.response.get("Error", {}).get("Code", "Unknown")
        error_message = error.response.get("Error", {}).get("Message", "")
        status_code = error.response.get("ResponseMetadata", {}).get(
            "HTTPStatusCode", 0
        )
        request_id = error.response.get("ResponseMetadata", {}).get("RequestId", "")

        # Get friendly error description if available
        error_description = COMMON_AWS_ERRORS.get(error_code, "")

        return {
            "error_code": error_code,
            "error_message": error_message,
            "status_code": status_code,
            "request_id": request_id,
            "description": error_description,
        }
    return {"error_type": type(error).__name__, "error_message": str(error)}


@dataclass
class CIDBConfig:
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
    # boto3 configuration
    max_attempts: int = 6
    mode: str = "standard"
    connect_timeout: int = 5  # Connection timeout in seconds
    read_timeout: int = 10  # Read timeout in seconds
    retries: dict = field(default_factory=dict)


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
                    att_dict[key] = {"DataType": "String", "StringValue": value}
                elif isinstance(value, bytes):
                    att_dict[key] = {"DataType": "Binary", "BinaryValue": value}

            # Convert message to JSON if it's a dict
            if isinstance(message, dict):
                message = json.dumps(message)

            # Publish the message
            response = topic.publish(Message=message, MessageAttributes=att_dict)
            message_id = response["MessageId"]
            logger.info(
                "Published message with attributes %s to topic %s.",
                attributes,
                topic_arn,
            )
        except ClientError:
            logger.exception("Couldn't publish message to topic %s.", topic_arn)
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
                "status": "completed",
                "total_messages": 0,
                "successful": 0,
                "failed": 0,
                "results": [],
            }

        total_messages = len(messages)
        logger.info("Sending %d messages to SNS topic %s", total_messages, topic_arn)

        # Get the topic
        topic = self.sns_resource.Topic(topic_arn)

        # Initialize counters and results
        successful_count = 0
        failed_count = 0
        results = []
        # DEBUG INIT
        dc = 0
        # DEBUG END
        # Process each message sequentially
        for index, message in enumerate(messages):
            try:
                # Extract message-specific attributes if available
                message_attributes = (
                    common_attributes.copy() if common_attributes else {}
                )

                if isinstance(message, dict) and "attributes" in message:
                    # Format attributes for SNS
                    for key, value in message["attributes"].items():
                        if isinstance(value, str):
                            message_attributes[key] = {
                                "DataType": "String",
                                "StringValue": value,
                            }
                        # TODO: Remove, no datatype binary provided
                        elif isinstance(value, bytes):
                            message_attributes[key] = {
                                "DataType": "Binary",
                                "BinaryValue": value,
                            }

                    # Use the actual message content
                    actual_message = message.get("message", message)
                else:
                    actual_message = message

                # Convert message to string if it's a dict
                if isinstance(actual_message, dict):
                    actual_message = json.dumps(actual_message)

                # Publish the message
                # DEBUG INIT

                if dc == 0:
                    logger.info(
                        f"debug: Batch  message: {actual_message}, Attributes: {message_attributes}"
                    )
                    dc = 1
                # DEBUG END
                logger.info()
                response = topic.publish(
                    Message=actual_message, MessageAttributes=message_attributes
                )
                message_id = response.get("MessageId")

                # Record success
                successful_count += 1
                results.append(
                    {"index": index, "status": "success", "MessageId": message_id}
                )

                logger.debug("Published message %d to topic %s", index, topic_arn)

            except Exception as e:
                # Record failure
                failed_count += 1
                results.append({"index": index, "status": "failed", "error": str(e)})

                logger.error(
                    "Failed to publish message %d to topic %s: %s",
                    index,
                    topic_arn,
                    str(e),
                )

        # Prepare summary
        summary = {
            "status": "completed",
            "total_messages": total_messages,
            "successful": successful_count,
            "failed": failed_count,
            "results": results,
        }

        logger.info(
            "Completed sending to SNS. Success: %d/%d, Failed: %d/%d",
            successful_count,
            total_messages,
            failed_count,
            total_messages,
        )

        return summary

    def publish_in_batches(
        self, topic_arn, policies, batch_size=10, common_attributes=None
    ):
        """
        Implements batching for SNS message publishing to improve performance and avoid throttling

        Args:
            topic_arn (str): The ARN of the SNS topic to publish to
            policies (list): List of policies or messages to publish
            batch_size (int, optional): Size of each batch (default: 10)
            common_attributes (dict, optional): Common message attributes for all messages

        Returns:
            dict: Summary of the batch publishing operation
        """
        if not policies:
            logger.warning("Empty policies list provided, nothing to send")
            return {
                "status": "completed",
                "total_messages": 0,
                "successful": 0,
                "failed": 0,
                "batches": 0,
                "results": [],
            }

        total_messages = len(policies)
        total_batches = math.ceil(total_messages / batch_size)

        logger.info(
            "Publishing %d messages to SNS topic %s in %d batches (batch size: %d)",
            total_messages,
            topic_arn,
            total_batches,
            batch_size,
        )

        # Initialize counters and results
        successful_count = 0
        failed_count = 0
        results = []

        # Process messages in batches
        for batch_index in range(total_batches):
            batch_start = batch_index * batch_size
            batch_end = min((batch_index + 1) * batch_size, total_messages)
            current_batch = policies[batch_start:batch_end]
            batch_size_actual = len(current_batch)

            logger.info(
                "Processing batch %d/%d with %d messages",
                batch_index + 1,
                total_batches,
                batch_size_actual,
            )

            # Prepare messages for this batch
            messages = [
                {"message": {"id": batch_start + i + 1, "data": policy}}
                for i, policy in enumerate(current_batch)
            ]

            # Get the topic
            topic = self.sns_resource.Topic(topic_arn)

            batch_start_time = time.time()
            batch_successful = 0
            batch_failed = 0
            # DEBUG INIT
            dc = 0
            # DEBUG END
            # Process each message in the batch
            for msg_index, message in enumerate(messages):
                absolute_index = batch_start + msg_index
                try:
                    # Extract message attributes
                    message_attributes = (
                        common_attributes.copy() if common_attributes else {}
                    )

                    if isinstance(message, dict) and "attributes" in message:
                        # Format attributes
                        for key, value in message["attributes"].items():
                            if isinstance(value, str):
                                message_attributes[key] = {
                                    "DataType": "String",
                                    "StringValue": value,
                                }
                            elif isinstance(value, bytes):
                                message_attributes[key] = {
                                    "DataType": "Binary",
                                    "BinaryValue": value,
                                }

                        # Use the actual message content
                        actual_message = message.get("message", message)
                    else:
                        actual_message = message

                    # Convert message to string if it's a dict
                    if isinstance(actual_message, dict):
                        actual_message = json.dumps(actual_message)
                    # DEBUG INIT
                    if dc == 0:
                        logger.info(
                            f"debug: Batch  message: {actual_message}, Attributes: {message_attributes}"
                        )
                    dc = 1
                    # DEBUG END
                    # Publish the message
                    response = topic.publish(
                        Message=actual_message, MessageAttributes=message_attributes
                    )
                    message_id = response.get("MessageId")

                    # Record success
                    successful_count += 1
                    batch_successful += 1
                    results.append(
                        {
                            "batch": batch_index + 1,
                            "index": absolute_index,
                            "status": "success",
                            "MessageId": message_id,
                        }
                    )

                except ClientError as ce:
                    # Handle AWS service errors
                    error_code = ce.response.get("Error", {}).get("Code", "Unknown")

                    failed_count += 1
                    batch_failed += 1
                    results.append(
                        {
                            "batch": batch_index + 1,
                            "index": absolute_index,
                            "status": "failed",
                            "error_code": error_code,
                            "error": str(ce),
                        }
                    )

                    logger.error(
                        "Failed to publish message %d (AWS error: %s): %s",
                        absolute_index,
                        error_code,
                        str(ce),
                    )

                except Exception as e:
                    # Handle general errors
                    failed_count += 1
                    batch_failed += 1
                    results.append(
                        {
                            "batch": batch_index + 1,
                            "index": absolute_index,
                            "status": "failed",
                            "error": str(e),
                        }
                    )

                    logger.error(
                        "Failed to publish message %d: %s", absolute_index, str(e)
                    )

            # Log batch results
            batch_duration = time.time() - batch_start_time
            logger.info(
                "Batch %d/%d completed in %.2fs - Success: %d/%d, Failed: %d/%d",
                batch_index + 1,
                total_batches,
                batch_duration,
                batch_successful,
                batch_size_actual,
                batch_failed,
                batch_size_actual,
            )

            # Add a small delay between batches to prevent throttling (if not the last batch)
            if batch_index < total_batches - 1:
                time.sleep(0.2)  # 200ms delay between batches

        # Prepare summary
        summary = {
            "status": "completed",
            "total_messages": total_messages,
            "successful": successful_count,
            "failed": failed_count,
            "batches": total_batches,
            "results": results,
        }

        logger.info(
            "SNS batch publishing complete - Success: %d/%d, Failed: %d/%d, Batches: %d",
            successful_count,
            total_messages,
            failed_count,
            total_messages,
            total_batches,
        )

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
            retries={"max_attempts": self.params.max_attempts, "mode": self.params.mode}
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
            if hasattr(self.client_session, "client"):
                # It's already a boto3.Session object
                boto3_session = self.client_session
            else:
                # It's our ClientSession class, so get the boto3.Session first
                boto3_session = self.client_session.get_session()

            return boto3_session.client(service_name, region_name=region_name)

        except ClientError as err:
            error_code, _ = extract_error_code(err)
            logger.error("Failed to get %s client: %s", service_name, error_code)
            raise
        except Exception as e:
            logger.error(
                "Unexpected error creating %s client: %s",
                service_name,
                type(e).__name__,
            )
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
            sts_client = self.get_client("sts")
        except ClientError as err:
            error_code, _ = extract_error_code(err)
            logger.error("Failed to create STS client: %s", error_code)
            # raise
            return None

        # Construct the full role ARN
        full_role_name = f"arn:aws:iam::{account_id}:role/{role_name}"

        try:
            logger.info("Assuming role in account %s", account_id)
            response = sts_client.assume_role(
                RoleArn=full_role_name,
                RoleSessionName="AWSAutoInventorySession",
                DurationSeconds=3600,
            )
        except ClientError as err:
            error_code, error_message = extract_error_code(err)

            if error_code == "AccessDenied":
                logger.error(
                    "Access denied for role %s in account %s", role_name, account_id
                )
            elif error_code == "InvalidClientTokenId":
                logger.error("Invalid credentials for account %s", account_id)
            else:
                logger.error(
                    "Failed to assume role in account %s: %s", account_id, error_code
                )

            # raise
            return None

        try:
            credentials = response["Credentials"]
            logger.info("Successfully assumed role in account %s", account_id)
            return boto3.Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )
        except KeyError:
            logger.error("Missing credentials in response for account %s", account_id)
            return None
        except Exception as err:
            logger.error(
                "Failed to create session for account %s: %s",
                account_id,
                type(err).__name__,
            )
            return None

    def generate_account_config(self, accounts=None, regions=None, role_name=None):
        """
        Generate a list of account configuration dictionaries based on provided accounts, regions, and IAM role name.

        Args:
            accounts (list, optional): List of AWS account IDs. If None, uses default account list.
            regions (list, optional): List of AWS regions to include. If None, uses default region list.
            role_name (str, optional): IAM role name to assume in each account.

        Returns:
            list: A list of dictionaries, each containing 'account_id', 'role_name', and 'regions' keys.

        """
        # Default values
        default_accounts = []
        default_regions = []

        # Use provided values or defaults
        account_ids = accounts if accounts else default_accounts
        region_list = regions if regions else default_regions

        # Generate configuration
        accounts_config = []
        for account_id in account_ids:
            accounts_config.append(
                {
                    "account_id": account_id,
                    "role_name": role_name,
                    "regions": region_list,
                }
            )

        return accounts_config
