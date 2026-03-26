# PropAI v30.0 - 루트 출력값
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "eks_cluster_name" {
  description = "EKS 클러스터 이름"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS API 엔드포인트"
  value       = module.eks.cluster_endpoint
}

output "rds_endpoint" {
  description = "RDS 엔드포인트"
  value       = module.rds.endpoint
}

output "redis_endpoint" {
  description = "Redis 엔드포인트"
  value       = module.redis.endpoint
}

output "s3_bucket_names" {
  description = "S3 버킷 이름 맵"
  value       = module.s3.bucket_names
}
