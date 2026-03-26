# PropAI v30.0 - RDS 모듈 (PostgreSQL 16 + PostGIS)

# ── 보안 그룹 ──
resource "aws_security_group" "rds" {
  name_prefix = "${var.name_prefix}-rds-"
  vpc_id      = var.vpc_id
  description = "RDS PostgreSQL 보안 그룹"

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
    description     = "EKS 노드에서 PostgreSQL 접근"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name_prefix}-rds-sg" }

  lifecycle { create_before_destroy = true }
}

# ── 파라미터 그룹 (PostGIS 활성화) ──
resource "aws_db_parameter_group" "main" {
  name   = "${var.name_prefix}-pg16-params"
  family = "postgres16"

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
}

# ── 서브넷 그룹 ──
resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-rds-subnet"
  subnet_ids = var.private_subnet_ids
  tags       = { Name = "${var.name_prefix}-rds-subnet" }
}

# ── RDS 인스턴스 ──
resource "aws_db_instance" "main" {
  identifier = "${var.name_prefix}-postgres"

  engine         = "postgres"
  engine_version = "16.3"
  instance_class = var.instance_class

  allocated_storage     = 100
  max_allocated_storage = 500
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "propai"
  username = "propai_admin"
  password = var.master_password

  multi_az               = var.multi_az
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.main.name

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name_prefix}-final-snapshot"

  performance_insights_enabled = true

  tags = { Name = "${var.name_prefix}-postgres" }
}
