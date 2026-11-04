# C08 release artifacts are separate from the Terraform state bucket.
data "aws_caller_identity" "current" {}

locals {
  artifact_bucket_name = "fairrent-artifacts-${data.aws_caller_identity.current.account_id}-eu-central-1"
  container_log_groups = {
    backend  = "/fairrent/dev/backend"
    frontend = "/fairrent/dev/frontend"
  }
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = local.artifact_bucket_name
  force_destroy = false
  tags          = { Name = "fairrent-artifacts", env = "S5" }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule { object_ownership = "BucketOwnerEnforced" }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_policy" "artifacts_tls" {
  bucket = aws_s3_bucket.artifacts.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyUnencryptedTransport", Effect = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.artifacts]
}

resource "aws_cloudwatch_log_group" "containers" {
  for_each          = local.container_log_groups
  name              = each.value
  retention_in_days = 14
  tags              = { env = "S5", service = each.key }
}

resource "aws_iam_role_policy" "runtime_artifacts_logs" {
  name = "fairrent-runtime-artifacts-logs"
  role = module.roles.role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        Resource = [for group in aws_cloudwatch_log_group.containers : "${trimsuffix(group.arn, ":*")}:*"]
      },
      {
        Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = aws_s3_bucket.artifacts.arn
      },
      {
        Effect    = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.artifacts.arn
        Condition = { StringLike = { "s3:prefix" = ["models", "models/*"] } }
      },
      {
        Effect   = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"]
        Resource = "${aws_s3_bucket.artifacts.arn}/models/*"
      }
    ]
  })
}

output "artifact_bucket_name" { value = aws_s3_bucket.artifacts.id }
output "container_log_groups" { value = local.container_log_groups }
