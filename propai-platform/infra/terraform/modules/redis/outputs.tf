# PropAI v30.0 - Redis 모듈 출력
output "endpoint" {
  description = "Redis 프라이머리 엔드포인트"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "port" {
  description = "Redis 포트"
  value       = 6379
}

output "connection_url" {
  description = "Redis 연결 URL"
  value       = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
}
