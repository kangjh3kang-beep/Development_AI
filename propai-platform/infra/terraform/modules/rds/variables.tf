# PropAI v30.0 - RDS 모듈 변수
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

variable "instance_class" {
  description = "RDS 인스턴스 클래스"
  type        = string
  default     = "db.r6g.large"
}

variable "master_password" {
  description = "마스터 비밀번호"
  type        = string
  sensitive   = true
}

variable "multi_az" {
  description = "Multi-AZ 배포 여부"
  type        = bool
  default     = true
}

variable "allowed_security_group_ids" {
  description = "접근 허용 보안 그룹 ID"
  type        = list(string)
}
