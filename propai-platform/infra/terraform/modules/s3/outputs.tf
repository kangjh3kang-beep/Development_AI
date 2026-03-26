# PropAI v30.0 - S3 모듈 출력
output "bucket_names" {
  description = "S3 버킷 이름 맵"
  value       = { for k, b in aws_s3_bucket.main : k => b.id }
}

output "bucket_arns" {
  description = "S3 버킷 ARN 맵"
  value       = { for k, b in aws_s3_bucket.main : k => b.arn }
}

output "bim_bucket_name" {
  description = "BIM 스토리지 버킷 이름"
  value       = aws_s3_bucket.main["bim"].id
}
