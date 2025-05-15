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

These types of resources are supported:
AWS: ~> 4.0
* [AWS Provider](https://www.terraform.io/docs/providers/aws/)

## Terraform Versions

Terraform: ~> 1.4
* Submit pull requests to `master` branch

## Application Information

* **AppID:** CIDB01
* **PointOfContact:** itawscoreservices@eatonvance.com
* **BusinessUnit:** Infrastructure
* **AppName** [cidb-application]
* **BusinessOwner**[ASwirski@eatonvance.com] 
* **Environment**[var.short_env]
* **SourceRepo**[github.com/Eaton-Vance-Corp/cidb-application]
* **SourceBranch**[master]
* **Team**[AWS Core Services]
* **SOXBackup**[NA]

## Reference Architecture / Diagram
* Link to diagram if applicable

## Terraform Version

* Terraform 1.4 

## Environments

|             Environment            	|        Ref       	|     Description    	|
|:----------------------------------:	|:----------------:	|:------------------:	|
|      Sandbox/Lower Development     	|   ?ref=ABC-123   	|    Local Branch    	|
| Development/Integrated Development 	| ?ref=Integration 	| Development Branch 	|
|              UAT/Test              	|    ?ref=master   	|    Master Branch   	|
|         Staging/Production         	|    ?ref=vx.y.z   	|   Release Branch   	|



## Risk Information

* **Public or Internal:** [Internal]
* **Data Type:** [Confidential]
* **Technologies In-Use:** [Terraform 1.4]
* **Compliance frameworks subject to:** []
* **Disaster Recovery Plan:** [ input dr plan here put NA if not applicable]
* **Overall Risk Rating:** [put risk rating, or put NA if app has not been reviewed]

## Rules to submit a change/how to deploy ##
* Submit pull requests to `master` branch (link doc)
