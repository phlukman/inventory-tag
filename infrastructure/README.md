# CIDB-Application -- AWS Native application
This repository provides the Terraform code for the infrastructure for the CIDB-application. The CIDB-application is the solution that Core Services has implemented in order to meet the MRA that requires Eaton Vance to have a method for sending over a full inventory of our AWS Environment to the MS Cloud Data Inventory.

## Account Stack
This infrastructure is only deployed to EV-ShareSvcNonprod and EV-ShareSvcProd, us-east-1

## Infrastructure
The following resources are created:
-S3 Bucket with appropirate policy
-IAM role with appropriate policy
-KMS key with appropriate policy
-Replication Rule
-additional required resources (policy attachments, etc.)

The S3 bucket collects data from AWS Config (TBD) and using the replication configuration, the IAM role pushes the data from the EV-S3 bucket to the MS-provided destination bucket. This is a daily snapshot of our entire AWS inventory.

## Tags:




These types of resources are supported:
AWS: ~> 4.0
* [AWS Provider](https://www.terraform.io/docs/providers/aws/)

## Terraform Versions

Terraform: ~> 1.4
* Submit pull requests to `master` branch

## To do:
-Update repository with prod values for sharesvcprod deployment (MS needs to create prod resources for production replication)
-Enable replication metrics and set up SNS to alert the team about replication failures.