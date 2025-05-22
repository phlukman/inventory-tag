data "aws_iam_policy_document" "ev_ecr_prisma_defender_policy" {
  version = "2012-10-17"
  statement {
    actions = [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:DescribeImages",
        "ecr:DescribeRepositories",
        "ecr:GetAuthorizationToken",
        "ecr:GetDownloadUrlForLayer",
        "ecr:GetRepositoryPolicy",
        "ecr:ListImages"
    ]
    effect    = "Allow"
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ev_ecr_prisma_defender_policy" {
  name        = "EvECRPrismaDefender"
  path        = "/"
  description = "Permissions required to enable Prisma Cloud for ECR Scanning"
  policy      = data.aws_iam_policy_document.ev_ecr_prisma_defender_policy.json
}

data "aws_iam_policy_document" "ev_ecr_prisma_defender_role" {
  version = "2012-10-17"
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = ["ecs.amazonaws.com"]
      type        = "Service"
    }
    effect = "Allow"
  }
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = ["*"]
      type        = "AWS"
    }
    condition {
      test = "StringEquals"
      values = [
        "435574127453", #evawssharesvcprod
        "477591219415"  #evawssharesvcnonprod
      ] 
      variable = "aws:PrincipalAccount"
    }
  }
}

resource "aws_iam_role" "ev_ecr_prisma_defender_role" {
  name               = "EvECRPrismaDefenderRole"
  assume_role_policy = data.aws_iam_policy_document.ev_ecr_prisma_defender_role.json
  path               = "/"
  tags = merge(var.tags, {
    Name = "EvECRPrismaDefenderRole"
  })
}

resource "aws_iam_role_policy_attachment" "EvECRPrismaDefenderPolicy_evecrprismadefenderole_policy_attachment" {
  role       = aws_iam_role.ev_ecr_prisma_defender_role.name
  policy_arn = aws_iam_policy.ev_ecr_prisma_defender_policy.arn
}
