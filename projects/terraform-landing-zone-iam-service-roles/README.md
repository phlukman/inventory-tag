# Terraform - AWS - Landing Zone - IAM Service Roles
Terraform module which produces IAM Service Roles for the EV AWS Landing Zone.

These types of resources are supported:
* [Data Source: aws_iam_policy_document](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document)
* [Resource: aws_iam_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy)
* [Resource: aws_iam_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role)
* [Resource: aws_iam_role_policy_attachment](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment)

## Terraform Versions

Terraform 0.12. Pin module source to ?ref=v1.0.2. Submit pull requests to `master` branch

## Usage

```hcl-terraform
module "iam_service_roles" {
  source        = "github.com/Eaton-Vance-Corp/terraform-aws-landing-zone-iam-service-roles?ref=v1.0.2"
  account_id    = "123456789012"
  tags          = local.tags
}
```

## Inputs

|    Name    |   Description  |     Type    | Default | Required |
|:----------:|:--------------:|:-----------:|:-------:|:--------:|
| account_id | AWS Account ID |    string   |   N/A   |    Yes   |
|    tags    |   Map of Tags  | map(string) |   null  |    No    |

## Import

```
terraform import module.region.module.global.module.iam_service_roles.aws_iam_policy.ev_cloud_watch_log_group_write_access_policy arn:aws:iam::123456789012:policy/service/CloudWatchLogGroupWrite
terraform import module.region.module.global.module.iam_service_roles.aws_iam_policy.ev_config_remediation_policy arn:aws:iam::123456789012:policy/EvConfigRemediationPolicy
terraform import module.region.module.global.module.iam_service_roles.aws_iam_policy.ev_s3_cross_region_replication_policy arn:aws:iam::123456789012:policy/EvS3CrossRegionReplicationPolicy
terraform import module.region.module.global.module.iam_service_roles.aws_iam_policy.ev_s3_logging_replication_policy arn:aws:iam::123456789012:policy/EvS3LoggingReplicationPolicy
terraform import module.region.module.global.module.iam_service_roles.aws_iam_policy.ev_ssm_automation_execution_policy arn:aws:iam::123456789012:policy/EVSSMAutomationExecutionPolicy
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role.ev_config_service ConfigService
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role.ev_lambda_exec LambdaExec
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role.ev_lambda_exec_stop_instances LambdaExecStopInstances
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role.ev_rds_monitoring_role EvRdsMonitoringRole
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role.ev_s3_cross_region_replication_role EvS3CrossRegionReplicationRole
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role.ev_s3_logging_replication_role EvS3LoggingReplicationRole
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role.ev_ssm_automation_execution_role EVSSMAutomationExecutionRole
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role.ev_vpc_flow_log_service_role VpcFlowLogService
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.AmazonEC2FullAccess_lambdaexecstopinstances_policy_attachment LambdaExecStopInstances/arn:aws:iam::aws:policy/AmazonEC2FullAccess
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.AmazonEC2ReadOnlyAccess_lambdaexec_policy_attachment LambdaExec/arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.AmazonRDSEnhancedMonitoringRole_evrdsmonitoringrole_policy_attachment EvRdsMonitoringRole/arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.AmazonRDSFullAccess_lambdaexecstopinstances_policy_attachment LambdaExecStopInstances/arn:aws:iam::aws:policy/AmazonRDSFullAccess
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.AmazonSNSRole_lambdaexec_policy_attachment LambdaExec/arn:aws:iam::aws:policy/service-role/AmazonSNSRole
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.AmazonSNSRole_lambdaexecstopinstances_policy_attachment LambdaExecStopInstances/arn:aws:iam::aws:policy/service-role/AmazonSNSRole
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.AWS_ConfigRole_configservice_policy_attachment ConfigService/arn:aws:iam::aws:policy/service-role/AWS_ConfigRole
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.CloudWatchLogGroupWrite_vpcflowlogservice_policy_attachment VpcFlowLogService/arn:aws:iam::123456789012:policy/CloudWatchLogGroupWrite
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.EvConfigRemediationPolicy_configservice_policy_attachment ConfigService/arn:aws:iam::123456789012:policy/EvConfigRemediationPolicy
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.EvS3CrossRegionReplicationPolicy_evs3crossregionreplicationrole_policy_attachment EvS3CrossRegionReplicationRole/arn:aws:iam::123456789012:policy/EvS3CrossRegionReplicationPolicy
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.EvS3LoggingReplicationPolicy_evs3loggingreplicationrole_policy_attachment EvS3LoggingReplicationRole/arn:aws:iam::123456789012:policy/EvS3LoggingReplicationPolicy
terraform import module.region.module.global.module.iam_service_roles.aws_iam_role_policy_attachment.EVSSMAutomationExecutionPolicy_evssmautomationexecutionrole_policy_attachment EVSSMAutomationExecutionRole/arn:aws:iam::123456789012:policy/EVSSMAutomationExecutionPolicy
```
