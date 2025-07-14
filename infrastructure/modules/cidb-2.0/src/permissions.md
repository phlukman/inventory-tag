
route53:ListHostedZones


tag:GetResources
----------------------------
cassandra:Select
#--------------------------
# Does not exist. Remove
#----------------------------
"cassandra:ListKeyspaces",
"cassandra:DescribeTable",
"cassandra:ListTagsForResource",

--------------------------------------------
appconfig:ListDeploymentStrategies

### Para ec2 Fleets
ec2:DescribeSpotFleetRequests (Pendiente)



calresearchsandbox (992854303108) x

evcesandbox (053210025230)

evgiqsandbox (175316323768)

evinfrassandbox (168002464918)

evinvesttechsandbox (984670241748)

evitrisksandbox (829689304269)

evsalesdistsandbox (119173687103)

ppacitizendevsandbox (286174197317)

ppacoresoftsyssandbox (511182126229)

ppadatamgtsandbox (453170101838)

ppaeicasandbox (362895556546)

ppagenaisandbox (767397819526)

ppainvestsyssandbox (658302302575)

pparesearchsandbox (131696788323)



```bash
 aws ec2 describe-spot-fleet-requests --region us-east-1
```

```text
An error occurred (AccessDenied) when calling the AssumeRole operation: User: arn:aws:sts::477591219415:assumed-role/ev_ms_cidb2_lambda_execute_role/dev-cidb2-collector-IAM is not authorized to perform: sts:AssumeRole on resource: arn:aws:iam::175316323768:role/EvResourceTagInventoryMemberAccountRole
```



"992854303108, 053210025230, 175316323768, 168002464918, 984670241748, 829689304269, 119173687103, 286174197317, 511182126229, 453170101838, 362895556546, 767397819526, 658302302575, 131696788323"