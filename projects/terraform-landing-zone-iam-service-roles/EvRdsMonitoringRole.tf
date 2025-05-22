data "aws_iam_policy_document" "ev_rds_monitoring_role" {
  version = "2012-10-17"
  statement {
    effect = "Allow"
    principals {
      identifiers = ["monitoring.rds.amazonaws.com"]
      type        = "Service"
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "ev_rds_monitoring_role" {
  name               = "EvRdsMonitoringRole"
  assume_role_policy = data.aws_iam_policy_document.ev_rds_monitoring_role.json
  path               = "/"
  tags = merge(var.tags, {
    "Name" = "EvRdsMonitoringRole"
  })
}

resource "aws_iam_role_policy_attachment" "AmazonRDSEnhancedMonitoringRole_evrdsmonitoringrole_policy_attachment" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
  role       = aws_iam_role.ev_rds_monitoring_role.name
}
