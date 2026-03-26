# PropAI v30.0 - 루트 변수 정의
variable "environment" {
  description = "배포 환경 (staging | production)"
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment는 staging 또는 production이어야 합니다."
  }
}

variable "aws_region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "프로젝트 이름"
  type        = string
  default     = "propai"
}

variable "vpc_cidr" {
  description = "VPC CIDR 블록"
  type        = string
  default     = "10.0.0.0/16"
}

variable "db_instance_class" {
  description = "RDS 인스턴스 클래스"
  type        = string
  default     = "db.r6g.large"
}

variable "db_password" {
  description = "RDS 마스터 비밀번호"
  type        = string
  sensitive   = true
}

variable "redis_node_type" {
  description = "ElastiCache 노드 타입"
  type        = string
  default     = "cache.r6g.large"
}

variable "eks_node_instance_types" {
  description = "EKS 노드 인스턴스 타입"
  type        = list(string)
  default     = ["m6i.xlarge"]
}

variable "eks_node_desired_size" {
  description = "EKS 노드 희망 수"
  type        = number
  default     = 3
}

variable "eks_node_min_size" {
  description = "EKS 노드 최소 수"
  type        = number
  default     = 2
}

variable "eks_node_max_size" {
  description = "EKS 노드 최대 수"
  type        = number
  default     = 6
}

variable "tags" {
  description = "공통 태그"
  type        = map(string)
  default     = {}
}
