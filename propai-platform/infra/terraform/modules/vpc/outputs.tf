# PropAI v30.0 - VPC 모듈 출력
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "퍼블릭 서브넷 ID 목록"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "프라이빗 서브넷 ID 목록"
  value       = aws_subnet.private[*].id
}

output "db_subnet_ids" {
  description = "DB 서브넷 ID 목록"
  value       = aws_subnet.db[*].id
}

output "db_subnet_group_name" {
  description = "DB 서브넷 그룹 이름"
  value       = aws_db_subnet_group.main.name
}

output "elasticache_subnet_group_name" {
  description = "ElastiCache 서브넷 그룹 이름"
  value       = aws_elasticache_subnet_group.main.name
}
