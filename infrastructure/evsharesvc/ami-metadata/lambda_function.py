import json
import boto3
import csv
import io
import os
import time
from datetime import datetime
from botocore.exceptions import ClientError

lambda_account          = os.environ['LAMBDA_ACCOUNT']
member_accounts         = json.loads(os.environ['MEMBER_ACCOUNTS'])
member_accounts_regions = ["us-east-1","us-east-2","us-west-2"]
member_accounts_role    = "EvMSCIDBAMIInventoryMemberAccountRole"
cidb_bucket_name        = f"{lambda_account}-us-east-1-priv-cidb-ev-logs"
csv_file_name           = f"AMIsMetadata/ami-metadata-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.csv"
sns_topic_arn           = os.environ['SNS_TOPIC_ARN']
cloudwatch_namespace    = "AMIInventoryLambda"

assume_role_success_list      = []
assume_role_fail_list         = []
get_ami_metadata_success_list = []
get_ami_metadata_fail_list    = []
s3_upload                     = []
error_messages                = []
s3_error_message              = ""

def log_time(start_time, message):
    print(f"{message}: {time.time() - start_time} seconds")

def put_custom_cloudwatch_metric_data(cw_client, cw_metric_name, cw_metric_value):
    log_event = {
        'MetricName': cw_metric_name,
        'Value': cw_metric_value,
        'Timestamp': datetime.now(timezone.utc).isoformat(),
        'Unit': 'Count'
    }
    print(json.dumps(log_event))
    cw_client.put_metric_data(
        Namespace=cloudwatch_namespace,
        MetricData=[
            {
                'MetricName': cw_metric_name,
                'Value': cw_metric_value,
                'Timestamp': datetime.now(timezone.utc),
                'Unit': 'Count'
            }
        ]
    )

def assume_role(account_id, region):
    try:
        sts_client = boto3.client('sts', region_name=region)
        assume_role_object = sts_client.assume_role(
            RoleArn=f"arn:aws:iam::{account_id}:role/{member_accounts_role}",
            RoleSessionName="CrossAccountAMIAccess"
        )
        assume_role_success_list.append(account_id)
        credentials = assume_role_object['Credentials']
        ec2_client = boto3.client(
            'ec2',
            region_name=region,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )
        return ec2_client
    except Exception as e:
        assume_role_fail_list.append(account_id)
        print(f"ERROR: Unexpected error {e} while assuming role {member_accounts_role} in account {account_id} and creating ec2 and sts boto3 clients")
        return None

def find_amis_in_use(ec2_client):
    public_amis_in_use = set()
    private_amis_in_use = set()
    paginator = ec2_client.get_paginator('describe_instances')
    for page in paginator.paginate():
        for reservation in page['Reservations']:
            for instance in reservation['Instances']:
                instance_state = instance['State']['Name']
                if instance_state in ['running', 'stopped']:
                    ami_id = instance['ImageId']
                    response = ec2_client.describe_images(ImageIds=[ami_id])
                    for image in response.get('Images',[]):
                        if image.get("Public", False):
                            public_amis_in_use.add(ami_id)
                        else:
                            private_amis_in_use.add(ami_id)                    
    return list(public_amis_in_use), list(private_amis_in_use)

def get_ami_info(ami_id, ec2_client):
    try:
        response = ec2_client.describe_images(ImageIds=[ami_id])
        images = response.get('Images', [])
        if images:
            image = images[0]
            is_public = image.get("Public", False)
            ami_metadata = {
                'id': image['ImageId'],
                'OWNER_ID': image.get('OwnerId', 'N/A'),
                'IMAGE_ID': image.get('ImageId', 'N/A'),
                'NAME': image.get('Name', 'N/A'),
                'PUBLIC': 'Yes' if is_public else 'No',
                'IMAGE_CREATION_DATE': image.get('CreationDate', 'N/A'),
                'TAGS': {tag['Key']: tag['Value'] for tag in image.get('Tags', [])}
            }
            return ami_metadata
        else:
            print(f"Error No information found for AMI ID {ami_id}")
            return None
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'InvalidAMIID.NotFound':
            print(f"Error AMI ID {ami_id} does not exist or is not accessible")
        else:
            print(f"Error occured in get_ami_info: {e}")
        return None

def describe_amis(ec2_client, is_public, account, region):
    filters = []
    amis = []
    paginator = ""
    if is_public:
        filters.append({'Name': 'is-public', 'Values': ['true']})
    else:
        filters.append({'Name': 'is-public', 'Values': ['false']})
    public_amis_in_use, private_amis_in_use = find_amis_in_use(ec2_client)
    paginator = ec2_client.get_paginator('describe_images')
    start_paginator = time.time()
    if is_public:
        if public_amis_in_use:
            for page in paginator.paginate(ImageIds=public_amis_in_use):
                amis.extend(page['Images'])
    else:
        for page in paginator.paginate(Filters=filters):
            amis.extend(page['Images'])
    log_time(start_paginator, f"Time to iterate for paginator for filters {filters} in {account} {region}")
    for ami in amis:
        if 'ImageId' not in ami:
            print(f"Error Missing 'ImageId' in AMI; {ami}")
    amis_dict = {ami['ImageId']: ami for ami in amis if 'ImageId' in ami}
    if not is_public:
        for ami in private_amis_in_use:
            if ami not in amis_dict:
                ami_metadata_to_add = get_ami_info(ami, ec2_client)
                if ami_metadata_to_add:
                    ami_metadata_to_add['ACCOUNT_ID'] = account
                    ami_metadata_to_add['REGION'] = region
                    amis_dict[ami] = ami_metadata_to_add
                else:
                    print(f"Error AMI {ami} metadata could not be retrieved")
    return amis

def upload_to_s3(all_amis_metadata):
    global s3_error_message
    csv_buffer = io.StringIO()
    csv_field_names = ['OWNER_ID', 'IMAGE_ID', 'NAME', 'PUBLIC', 'IMAGE_CREATION_DATE', 'TAGS', 'ACCOUNT_ID', 'REGION']
    csv_writer = csv.DictWriter(csv_buffer, fieldnames=csv_field_names)
    csv_writer.writeheader()
    for ami_metadata in all_amis_metadata:            
        csv_writer.writerow(ami_metadata)
    regional_s3_client = boto3.client('s3', region_name='us-east-1')
    try:
        regional_s3_client.put_object(
            Bucket = cidb_bucket_name,
            Key = csv_file_name,
            Body = csv_buffer.getvalue(),
            ContentType = 'text/csv'
        )
    except Exception as e:
        s3_error_message = f"ERROR: Unexpted error {e} while uploading file {csv_file_name} to cidb s3 bucket {cidb_bucket_name}"
        print(s3_error_message)
        s3_upload.append(s3_error_message)


def collect_unique_amis_metadata():
    unique_amis = set()
    all_amis = []
    for account in member_accounts:
        for region in member_accounts_regions:
            try:
                regional_ec2_client = assume_role(account, region)
                for is_public in [False, True]:
                    start = time.time()
                    amis = describe_amis(regional_ec2_client, is_public, account, region)
                    log_time(start, f"Time to describe_amis in {account} {region} {is_public}")
                    start = time.time()
                    for ami in amis:
                        ami_id = ami['ImageId']
                        if ami_id not in unique_amis:
                            unique_amis.add(ami_id)                       
                            all_amis.append({
                                'OWNER_ID': ami.get('OwnerId', 'N/A'),
                                'IMAGE_ID': ami.get('ImageId', 'N/A'),
                                'NAME': ami.get('Name', 'N/A'),
                                'PUBLIC': 'Yes' if is_public else 'No',
                                'IMAGE_CREATION_DATE': ami.get('CreationDate', 'N/A'),
                                'TAGS': {tag['Key']: tag['Value'] for tag in ami.get('Tags', [])},
                                'ACCOUNT_ID': account,
                                'REGION': region
                            })
                    log_time(start, f"Time to iterate over amis {account} {region} {is_public}")
                get_ami_metadata_success_list.append(f"{account}_{region}")
            except Exception as e:
                get_ami_metadata_fail_list.append(f"{account}_{region}")
                print(f"ERROR: Unexpected error {e} while processing ami metadata for account {account} region {region}")
    return all_amis

def lambda_handler(event, context):
    all_amis_metadata = collect_unique_amis_metadata()
    upload_to_s3(all_amis_metadata)
    sns_client = boto3.client('sns')

    if assume_role_fail_list != []:
        assume_role_fail_set = set(assume_role_fail_list)
        print(f"ERROR: Assume Role failed for accounts: {assume_role_fail_set}")
        error_messages.append(f"ERROR: Assume Role failed for accounts: {assume_role_fail_set}")

    if get_ami_metadata_fail_list != []:
        get_ami_metadata_fail_set = set(get_ami_metadata_fail_list)
        print(f"ERROR: Getting AMI Metadata failed for accounts/regions: {get_ami_metadata_fail_set}")
        error_messages.append(f"ERROR: Getting AMI Metadata failed for accounts/regions: {get_ami_metadata_fail_set}")

    if s3_upload != []:
        print(f"ERROR: Uploading to s3: {s3_error_message}")
        error_messages.append(f"ERROR: Uploading to s3: {s3_error_message}")

    if error_messages != []:
        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject='CIDB AMI Lambda Failures',
            Message='\n'.join(error_messages)
        )
    else:
        print(f"SUCCESS: AMI Information retrieved from all member accounts and uploaded to cidb bucket successfully")