# PropAI v30.0 - EKS 모듈 변수
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

variable "node_instance_types" {
  description = "노드 인스턴스 타입"
  type        = list(string)
  default     = ["m6i.xlarge"]
}

variable "node_desired_size" {
  description = "노드 희망 수"
  type        = number
  default     = 3
}

variable "node_min_size" {
  description = "노드 최소 수"
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "노드 최대 수"
  type        = number
  default     = 6
}
