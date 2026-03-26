# PropAI v30.0 - 프로덕션 환경
module "infrastructure" {
  source = "../../"

  environment = "production"
  aws_region  = "ap-northeast-2"

  vpc_cidr          = "10.1.0.0/16"
  db_instance_class = "db.r6g.xlarge"
  db_password       = var.db_password
  redis_node_type   = "cache.r6g.large"

  eks_node_instance_types = ["m6i.xlarge"]
  eks_node_desired_size   = 3
  eks_node_min_size       = 2
  eks_node_max_size       = 8

  tags = {
    Environment = "production"
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
