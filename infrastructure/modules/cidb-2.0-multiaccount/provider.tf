# Source provider it's default provider

#This provider is used to create policy and role in the target account    
# provider "aws" {
#   region = "us-east-1"
#   alias  = "target_0"
#   # Either direct credentials or assume role
#   assume_role {
#     role_arn = "arn:aws:iam::477591219415:role/OrganizationAccountAccessRole"
#   }
# }

# provider "aws" {
#   region = "us-east-1"
#   alias  = "target_1"
#   assume_role {
#     role_arn = "arn:aws:iam::477591219415:role/OrganizationAccountAccessRole"
#   }
# }