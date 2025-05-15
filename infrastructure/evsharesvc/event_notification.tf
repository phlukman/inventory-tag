resource "aws_s3_bucket_notification" "cidb_replication_fail_notif" {
  bucket = module.cidb_s3_bucket.s3_bucket.id

  topic {
    topic_arn = module.cidb_sns_topic.sns_topic.arn
    events    = ["s3:Replication:OperationFailedReplication"]
  }
}
