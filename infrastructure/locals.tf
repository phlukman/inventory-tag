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

