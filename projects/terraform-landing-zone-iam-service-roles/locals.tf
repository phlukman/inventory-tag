locals {
  path = "/service/"
  enable_sandbox = length(regexall(".*sandbox.*", var.account_alias)) > 0 ? true : false
  enable_nonprod = length(regexall(".*nonprod.*", var.account_alias)) > 0 ? true : false
  enable_prod = local.enable_sandbox || local.enable_nonprod ? false : true
  evsharesvcnonprod_lambda_exec_role = "arn:aws:iam::477591219415:role/EvMSCIDBAMIInventorySharedSvcLambdaExecRole"
  evsharesvcprod_lambda_exec_role = "arn:aws:iam::435574127453:role/EvMSCIDBAMIInventorySharedSvcLambdaExecRole"
  cidb_lambda_exec_role_arns = local.enable_prod ? [ local.evsharesvcprod_lambda_exec_role ] : [ local.evsharesvcnonprod_lambda_exec_role, local.evsharesvcprod_lambda_exec_role ]
  evitrisksandbox_lambda_exec_role = "arn:aws:iam::829689304269:role/devstaaxus-east-1TaskRole"
  evitrisnonprod_lambda_exec_role = "arn:aws:iam::633763041547:role/uatstaaxus-east-1TaskRole"
  evitriskprod_lambda_exec_role = "arn:aws:iam::435574186070883872127453:role/prodstaaxus-east-1TaskRole"
  staax_lambda_exec_role_arns = local.enable_sandbox ? [ local.evitrisksandbox_lambda_exec_role ] : local.enable_nonprod ? [ local.evitrisksandbox_lambda_exec_role, local.evitrisnonprod_lambda_exec_role ] : [ local.evitrisksandbox_lambda_exec_role, local.evitrisnonprod_lambda_exec_role, local.evitriskprod_lambda_exec_role ]
}
