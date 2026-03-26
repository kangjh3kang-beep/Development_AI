# PropAI v30.0 - 스테이징 환경
module "infrastructure" {
  source = "../../"

  environment = "staging"
  aws_region  = "ap-northeast-2"

  vpc_cidr          = "10.0.0.0/16"
  db_instance_class = "db.t3.medium"
  db_password       = var.db_password
  redis_node_type   = "cache.t3.medium"

  eks_node_instance_types = ["m6i.large"]
  eks_node_desired_size   = 2
  eks_node_min_size       = 1
  eks_node_max_size       = 4

  tags = {
    Environment = "staging"
    Team        = "propai"
  }
}

variable "db_password" {
  description = "RDS 마스터 비밀번호"
  type        = string
  sensitive   = true
}

output "eks_cluster_name" {
  value = module.infrastructure.eks_cluster_name
}

output "rds_endpoint" {
  value = module.infrastructure.rds_endpoint
}
