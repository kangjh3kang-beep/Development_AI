# PropAI v30.0 - VPC 모듈 변수
variable "name_prefix" {
  description = "리소스 이름 접두사"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR 블록"
  type        = string
}

variable "aws_region" {
  description = "AWS 리전"
  type        = string
}
