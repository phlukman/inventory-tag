locals {
  tags = {
    "AppID"                   = "CIDB01"
    "AppName"                 = "cidb-application"
    "BusinessUnit"            = "Infrastructure"
    "Environment"             = var.short_env
    "PointOfContact"          = "cloud-im-bue-aws@morganstanley.com"
    "Repository"              = "https://github.com/Eaton-Vance-Corp/cidb-application"
    "Team"                    = "AWS IM BUE"
    "TeamManager"             = "Alec Swirski"
    "Tier"                    = "Infrastructure"
    "Soxbackup"               = "NA"
    "fin_billing_eon_id"      = "298390"
    "fin_billing_model"       = "dedicated"
    "fin_billing_environment" = var.fin_billing_env
    "inv_eon_id"              = "298390"
    "sec_approval"            = "cloudsecarch-36655264"
    "sec_data_sensitivity"    = "confidental"
    "obs_owning_contact"      = "cloud-im-bue-aws@morganstanley.com"
  }
}
locals {
  availability_zones = [for subnet in module.defaults.private_subnets : subnet.availability_zone]
  subnet_ids         = [for subnet in module.defaults.private_subnets : subnet.id]
}
locals {
  accessibility = "priv"
}
locals {
  account_alias                 = data.aws_iam_account_alias.current.account_alias
  account_id                    = data.aws_caller_identity.current.account_id
  ev_member_account_ids_sandbox = ["992854303108", "131696788323", "453170101838", "658302302575", "767397819526", "511182126229", "286174197317", "362895556546", "462415392569", "829689304269", "168002464918", "119173687103", "984670241748", "175316323768", "053210025230"]
  ev_member_account_ids_nonprod = ["477591219415", "774964446426", "648478090239", "106305399484", "071703922629", "746724791886", "253295566561", "633763041547", "689208158427", "925507843314", "912981319707", "173053452863", "201872524245", "698165960104", "360201401833", "928079129283", "891377357498"]
  ev_member_account_ids_prod    = ["253091533528", "575396202922", "435574127453", "450671918739", "895720729878", "667678310459", "187614575543", "423339021197", "050170277551", "155051631857", "783060173409", "059997061947", "186070883872", "247462361306", "528292876888", "498105692602", "273753702448", "949235798774", "318750475888", "580501918923", "267821145838", "381492315486"]
  member_account_ids            = local.account_alias == "evsharesvcnonprod" ? flatten([local.ev_member_account_ids_sandbox, local.ev_member_account_ids_nonprod]) : local.account_alias == "evsharesvcprod" ? flatten([local.ev_member_account_ids_sandbox, local.ev_member_account_ids_nonprod, local.ev_member_account_ids_prod]) : []
  engineer_role_arn             = local.account_alias == "evsharesvcnonprod" ? "arn:aws:iam::477591219415:role/Engineer" : local.account_alias == "evsharesvcprod" ? "arn:aws:iam::435574127453:role/Engineer" : ""
}

# locals {
#   service_by_category = {
#     IAM = [
#       "AWS::IAM::Policy"
#     ],
#     KMS = [
#       "AWS::KMS::Alias"
#     ],
#     CW = [
#       "AWS::CloudWatch::Alarm"
#     ],
#     EC2Code = [
#       "AWS::EC2::EC2Fleet"
#     ]
#     EVENT_RULE = [
#       "AWS::Events::Rule"
#     ],
#     MISC = [
#       "AWS::Route53::HostedZone",
#       "AWS::AppConfig::DeploymentStrategy",
#       "AWS::AutoScaling::ScalingPolicy",
#       "AWS::Cassandra::Keyspace",
#       "AWS::AppConfig::DeploymentStrategy"
#     ]
#   }
# }

locals {
  service_by_category = {
    IAM = [
      "AWS::IAM::Policy"
    ],
    KMS = [
      "AWS::KMS::Alias"
    ],
  }
}