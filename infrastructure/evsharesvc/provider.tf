provider "aws" {
  region = var.region
  default_tags {
    tags = local.tags
  }
}

provider "aws" {
  region = var.region
  alias  = "use1"
  default_tags {
    tags = local.tags
  }
}

provider "aws" {
  alias  = "use2"
  region = "us-east-2"
  default_tags {
    tags = local.tags
  }
}

provider "aws" {
  alias  = "usw2"
  region = "us-west-2"
  default_tags {
    tags = local.tags
  }
}
