# At the top of your module, add this provider configuration
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
    }
  }
}