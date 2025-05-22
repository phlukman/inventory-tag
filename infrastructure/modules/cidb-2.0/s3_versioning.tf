/**
 * S3 Bucket Versioning and Lifecycle Configuration
 * 
 * This file adds versioning and lifecycle policies to the S3 bucket used by the CIDB 2.0 module.
 * These configurations solve the concurrency issues when multiple Lambda functions try to update
 * the same file by leveraging S3's native versioning capabilities.
 */

resource "aws_s3_bucket_versioning" "cidb2_bucket_versioning" {
  bucket = var.s3_bucket_name

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "cidb2_bucket_lifecycle" {
  # Make sure versioning is enabled before creating lifecycle rules
  depends_on = [aws_s3_bucket_versioning.cidb2_bucket_versioning]

  bucket = var.s3_bucket_name

  # Rule for managing versions of all objects
  rule {
    id     = "expire-old-versions-7days"
    status = "Enabled"

    # Expire noncurrent versions after 7 days
    noncurrent_version_expiration {
      noncurrent_days = 7
    }

    # Clean up any incomplete multipart uploads after 1 day
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}
