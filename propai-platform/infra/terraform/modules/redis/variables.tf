# PropAI v30.0 - Redis 모듈 변수
variable "name_prefix" {
  description = "리소스 이름 접두사"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "프라이빗 서브넷 ID 목록"
  type        = list(string)
}

variable "node_type" {
  description = "ElastiCache 노드 타입"
  type        = string
  default     = "cache.r6g.large"
}

variable "num_cache_clusters" {
  description = "캐시 클러스터 수 (레플리카 포함)"
  type        = number
  default     = 2
}

variable "allowed_security_group_ids" {
  description = "접근 허용 보안 그룹 ID"
  type        = list(string)
}
