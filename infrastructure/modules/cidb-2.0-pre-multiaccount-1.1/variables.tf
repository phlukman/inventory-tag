/**
 * Variables for S3 bucket versioning and lifecycle configuration
 * 
 * These variables match the ones in the original CIDB 2.0 module.
 */

variable "s3_bucket_name" {
  description = "S3 bucket name where the CIDB data will be stored"
  type        = string
}

variable "s3_bucket_arn" {
  description = "S3 bucket ARN where the CIDB data will be stored"
  type        = string
}
