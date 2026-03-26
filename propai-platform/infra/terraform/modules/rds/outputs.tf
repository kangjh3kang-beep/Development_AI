# PropAI v30.0 - RDS 모듈 출력
output "endpoint" {
  description = "RDS 엔드포인트"
  value       = aws_db_instance.main.endpoint
}

output "address" {
  description = "RDS 호스트 주소"
  value       = aws_db_instance.main.address
}

output "port" {
  description = "RDS 포트"
  value       = aws_db_instance.main.port
}

output "db_name" {
  description = "데이터베이스 이름"
  value       = aws_db_instance.main.db_name
}
