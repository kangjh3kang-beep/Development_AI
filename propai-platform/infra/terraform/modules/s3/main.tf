# PropAI v30.0 - S3 모듈 (BIM, 문서, 백업)

locals {
  buckets = {
    bim     = "${var.name_prefix}-bim-storage"
    docs    = "${var.name_prefix}-documents"
    backups = "${var.name_prefix}-backups"
  }
}

# ── S3 버킷 ──
resource "aws_s3_bucket" "main" {
  for_each = local.buckets
  bucket   = each.value
  tags     = { Name = each.value, Purpose = each.key }
}

# ── 버전 관리 ──
resource "aws_s3_bucket_versioning" "main" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.main[each.key].id

  versioning_configuration {
    status = "Enabled"
  }
}

# ── 서버 사이드 암호화 ──
resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.main[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

# ── 퍼블릭 액세스 차단 ──
resource "aws_s3_bucket_public_access_block" "main" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.main[each.key].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── 수명주기 규칙 (백업 버킷만) ──
resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.main["backups"].id

  rule {
    id     = "archive-old-backups"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    expiration {
      days = 365
    }
  }
}

# ── CORS 설정 (BIM 버킷 — 프론트엔드 업로드용) ──
resource "aws_s3_bucket_cors_configuration" "bim" {
  bucket = aws_s3_bucket.main["bim"].id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = var.environment == "production" ? ["https://app.propai.io"] : ["*"]
    max_age_seconds = 3600
  }
}
