#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lambda function to list all AWS accounts in an organization with role assumption capability
"""
import os
import json
import sys
import logging
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Constants
ROLE_TO_ASSUME = os.environ.get(
    "ROLE_TO_ASSUME", "EvResourceTagInventoryMemberAccountRole"
)
OUTPUT_BUCKET = os.environ.get("BUCKET_NAME")
MANAGEMENT_ACCOUNT_ID = os.environ.get("MANAGEMENT_ACCOUNT_ID", "")
MANAGEMENT_ROLE_NAME = os.environ.get(
    "MANAGEMENT_ROLE_NAME", "OrganizationAccountAccessRole"
)
ENV_EXCLUDED_ACCOUNTS = json.loads(os.environ.get("ENV_EXCLUDED_ACCOUNTS", "[]"))


class OrganizationAccountsLister:
    def __init__(self):
        """
        Initialize the OrganizationAccountsLister with AWS clients
        """
        # Standard clients for the execution environment
        self.sts_client = boto3.client("sts")
        self.s3_client = boto3.client("s3")
        try:
            # Get organization client - either through role assumption or directly
            logger.info(
                f"Attempting to assume role in management account {MANAGEMENT_ACCOUNT_ID}"
            )
            management_session = self.assume_role(
                MANAGEMENT_ACCOUNT_ID, MANAGEMENT_ROLE_NAME
            )
            self.organizations_client = management_session.client("organizations")
            logger.info("Successfully created organizations client with assumed role")
        except ClientError as e:
            logger.error(
                f"Failed to assume role in management account {MANAGEMENT_ACCOUNT_ID}: {str(e)}"
            )
            raise RuntimeError(f"Failed to initialize Organizations client: {str(e)}")

    def assume_role(self, account_id, role_name):
        """
        Assume a role in another account

        Args:
            account_id (str): The AWS account ID to assume role in
            role_name (str): The name of the role to assume

        Returns:
            boto3.Session or None: The assumed role session or None if failed
        """
        try:
            role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
            response = self.sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"ListAccountsSession-{account_id}",
                DurationSeconds=900,  # 15 minutes
            )

            credentials = response["Credentials"]
            session = boto3.Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )
            logger.info(
                f"Successfully assumed role {role_name} in account {account_id}"
            )
            return session
        except ClientError as e:
            logger.error(f"Error assuming role in account {account_id}: {str(e)}")
            return None

    def list_accounts(self, excluded_accounts=None):
        """
        List all accounts in the organization, excluding specified accounts

        Args:
            excluded_accounts (list, optional): List of account IDs to exclude from the results

        Returns:
            list: List of dictionaries containing account details
        """
        try:
            accounts = []
            # Initialize excluded_accounts to empty list if None
            if excluded_accounts is None:
                excluded_accounts = []

            logger.info(
                f"Will exclude {len(excluded_accounts)} accounts from the listing"
            )

            # Now proceed with listing accounts
            paginator = self.organizations_client.get_paginator("list_accounts")

            for page in paginator.paginate():
                for account in page.get("Accounts", []):
                    # Only include active accounts that are not in the exclusion list
                    if (
                        account["Status"] == "ACTIVE"
                        and account["Id"] not in excluded_accounts
                    ):
                        accounts.append(
                            {
                                "AccountId": account["Id"],
                                "AccountName": account["Name"],
                                "AccountEmail": account["Email"],
                                "JoinedMethod": account.get("JoinedMethod", "Unknown"),
                                "JoinedTimestamp": (
                                    account.get("JoinedTimestamp", "").isoformat()
                                    if account.get("JoinedTimestamp")
                                    else None
                                ),
                            }
                        )
                    elif (
                        account["Status"] == "ACTIVE"
                        and account["Id"] in excluded_accounts
                    ):
                        logger.info(
                            f"Excluding account {account['Id']} ({account.get('Name', 'Unknown')}) as requested"
                        )

            logger.info(
                f"Found {len(accounts)} active accounts in the organization (after excluding {len(excluded_accounts)} accounts)"
            )
            return accounts
        except ClientError as e:
            logger.error(f"Error listing accounts: {str(e)}")
            return []

    def list_account_details(self, excluded_accounts=None):
        """
        List accounts with additional details through role assumption

        Args:
            excluded_accounts (list, optional): List of account IDs to exclude from the results

        Returns:
            list: List of dictionaries containing extended account details
        """
        accounts = self.list_accounts(excluded_accounts)
        extended_accounts = []

        for account in accounts:
            account_id = account["AccountId"]
            extended_info = account.copy()
            extended_info["AccountAliases"] = []

            # Get account tags from Organizations API
            try:
                tags = self.get_account_tags(account_id)
                # Convert to dictionary format for easier use
                tags_dict = {tag["Key"]: tag["Value"] for tag in tags}
                tags_json = json.dumps(tags_dict).replace('"', "'")

                extended_info["Tags"] = tags_json  # Store tags in CSV-friendly format
                extended_info["RawTags"] = tags  # Keep the original format too
            except Exception as e:
                logger.warning(f"Couldn't get tags for account {account_id}: {str(e)}")
                extended_info["Tags"] = {}
                extended_info["RawTags"] = []

            # Get OU path from Organizations API
            try:
                ou_info = self.get_account_ou_path(account_id)
                extended_info["OUPath"] = ou_info["Path"]
                extended_info["OUId"] = ou_info["OUId"]
                extended_info["OUName"] = ou_info["OUName"]
            except Exception as e:
                logger.warning(
                    f"Couldn't get OU path for account {account_id}: {str(e)}"
                )
                extended_info["OUPath"] = "/"
                extended_info["OUId"] = ""
                extended_info["OUName"] = ""

            # Try to assume role in the account for additional information
            assumed_session = self.assume_role(account_id, ROLE_TO_ASSUME)
            if assumed_session:
                # Try to get account aliases
                try:
                    iam_client = assumed_session.client("iam")
                    aliases_response = iam_client.list_account_aliases()
                    aliases = aliases_response.get("AccountAliases", [])
                    extended_info["AccountAliases"] = aliases
                except Exception as e:
                    logger.warning(
                        f"Couldn't get account aliases for {account_id}: {str(e)}"
                    )
            extended_accounts.append(extended_info)
        logger.info(
            f"Collected extended information for {len(extended_accounts)} accounts"
        )
        return extended_accounts

    def get_account_tags(self, account_id):
        """
        Get tags for an AWS account

        Args:
            account_id (str): The AWS account ID

        Returns:
            list: List of tag dictionaries with keys 'Key' and 'Value'
        """
        try:
            response = self.organizations_client.list_tags_for_resource(
                ResourceId=account_id
            )
            tags = response.get("Tags", [])
            logger.info(f"Retrieved {len(tags)} tags for account {account_id}")
            return tags
        except ClientError as e:
            logger.error(f"Error retrieving tags for account {account_id}: {str(e)}")
            return []

    def get_account_ou_path(self, account_id):
        """
        Get the full OU path for an AWS account

        Args:
            account_id (str): The AWS account ID

        Returns:
            dict: Dictionary containing OU information including full path
        """
        try:
            # First get the root ID
            roots_response = self.organizations_client.list_roots()
            if not roots_response.get("Roots"):
                logger.warning(f"No organization roots found")
                return {"Path": "/", "OUId": "", "OUName": ""}

            root_id = roots_response["Roots"][0]["Id"]

            # Get the parent for this account
            parents_response = self.organizations_client.list_parents(
                ChildId=account_id
            )

            if not parents_response.get("Parents"):
                logger.warning(f"No parent found for account {account_id}")
                return {"Path": "/", "OUId": "", "OUName": ""}

            parent = parents_response["Parents"][0]
            parent_id = parent["Id"]
            parent_type = parent["Type"]

            # If parent is root, return simple path
            if parent_type == "ROOT":
                return {"Path": "/", "OUId": root_id, "OUName": "Root"}

            # Otherwise build the OU path
            ou_response = self.organizations_client.describe_organizational_unit(
                OrganizationalUnitId=parent_id
            )
            current_ou = ou_response["OrganizationalUnit"]
            current_ou_name = current_ou["Name"]
            current_ou_id = current_ou["Id"]

            # Build full path by traversing up the tree
            path_components = [current_ou_name]
            current_parent_id = parent_id

            while True:
                try:
                    parent_of_ou_response = self.organizations_client.list_parents(
                        ChildId=current_parent_id
                    )

                    if not parent_of_ou_response.get("Parents"):
                        break

                    ou_parent = parent_of_ou_response["Parents"][0]
                    current_parent_id = ou_parent["Id"]
                    parent_type = ou_parent["Type"]

                    # If we've reached the root, stop
                    if parent_type == "ROOT":
                        break

                    # Otherwise get the OU name and continue
                    ou_info_response = (
                        self.organizations_client.describe_organizational_unit(
                            OrganizationalUnitId=current_parent_id
                        )
                    )
                    ou_name = ou_info_response["OrganizationalUnit"]["Name"]
                    path_components.append(ou_name)

                except ClientError as e:
                    logger.error(
                        f"Error traversing OU path at {current_parent_id}: {str(e)}"
                    )
                    break

            # Reverse and format the path
            path_components.reverse()
            full_path = "/" + "/".join(path_components)

            return {"Path": full_path, "OUId": current_ou_id, "OUName": current_ou_name}

        except ClientError as e:
            logger.error(f"Error retrieving OU path for account {account_id}: {str(e)}")
            return {"Path": "/", "OUId": "", "OUName": ""}

    def save_to_s3_csv(self, accounts, filename):
        """
        Save account information to S3 bucket in CSV format

        Args:
            accounts (list): List of account dictionaries
            filename (str): The filename to use in S3

        Returns:
            bool: True if successful, False otherwise
        """
        if not OUTPUT_BUCKET:
            logger.warning("No S3 bucket specified, skipping CSV S3 upload")
            return False

        try:
            # Create CSV content with headers
            csv_content = "AccountId,AccountAlias,OUPath,Tags\n"

            # Add data for each account
            for account in accounts:
                account_id = account.get("AccountId", "")
                # Simplified account alias handling - just get the first one if available
                account_aliases = account.get("AccountAliases", [])
                if account_aliases and len(account_aliases) > 0:
                    account_alias = account_aliases[0]  # Just take the first alias
                else:
                    account_alias = "NA"  # Use NA as fallback

                ou_path = account.get("OUPath", "/")

                # Keep tags in JSON format as requested
                tags = account.get("Tags", {})
                json_tags = json.dumps(tags) if tags else "{}"

                # Add row to CSV (properly escaping values that might contain commas)
                csv_content += (
                    f'{account_id},"{account_alias}","{ou_path}",{json_tags}\n'
                )

            # Upload to S3
            self.s3_client.put_object(
                Bucket=OUTPUT_BUCKET,
                Key=filename,
                Body=csv_content,
                ContentType="text/csv",
            )
            logger.info(
                f"Successfully saved CSV data to s3://{OUTPUT_BUCKET}/{filename}"
            )
            return True
        except Exception as e:
            logger.error(f"Error saving CSV to S3: {str(e)}")
            return False


def lambda_handler(event, context):
    """
    Lambda handler function

    Args:
        event (dict): Lambda event containing optional 'excluded_accounts' list
        context (object): Lambda context

    Returns:
        dict: Response with accounts information
    """
    try:
        logger.info("Starting AWS Organization accounts listing")
        logger.info(f"Event details: {json.dumps(event)}")
        today = datetime.today()
        year = today.strftime("%Y")
        month = today.strftime("%B").lower()
        day = today.strftime("%d")
        OBJECT_KEY = (
            f"Custom/AWS-ORG-Accounts/AWS-ORG-Accounts-{year}-{month}-{day}.csv"
        )

        # Initialize the OrganizationAccountsLister
        lister = OrganizationAccountsLister()

        # Get detailed account information including tags and OU paths
        accounts = lister.list_account_details(ENV_EXCLUDED_ACCOUNTS)
        logger.info(f"Retrieved detailed information for {len(accounts)} accounts")
        # save to S3
        lister.save_to_s3_csv(accounts, OBJECT_KEY)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": f"Successfully processed {len(accounts)} AWS organization accounts",
                    "total_accounts": len(accounts),
                    "accounts_with_tags": sum(
                        1
                        for acc in accounts
                        if acc.get("Tags") and len(acc.get("Tags", {})) > 0
                    ),
                    "accounts_with_ou_path": sum(
                        1
                        for acc in accounts
                        if acc.get("OUPath") and acc["OUPath"] != "/"
                    ),
                    "output_formats": ["json", "csv"],
                    "output_path": OBJECT_KEY,
                }
            ),
        }
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"message": f"Error processing AWS organization accounts: {str(e)}"}
            ),
        }
