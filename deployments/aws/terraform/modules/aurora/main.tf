resource "random_password" "master" {
  length  = 32
  special = true
}

resource "aws_secretsmanager_secret" "db_password" {
  name_prefix = "${var.cluster_identifier}-password-"
  description = "Master password for ${var.cluster_identifier}"

  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.master.result
}

resource "aws_db_subnet_group" "aurora" {
  name       = "${var.cluster_identifier}-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.cluster_identifier}-subnet-group"
  }
}

resource "aws_security_group" "aurora" {
  name_prefix = "${var.cluster_identifier}-sg-"
  description = "Security group for ${var.cluster_identifier}"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from EKS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_groups
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.cluster_identifier}-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_rds_cluster" "aurora" {
  cluster_identifier = var.cluster_identifier
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = "15.4"
  database_name      = var.database_name
  master_username    = var.master_username
  master_password    = random_password.master.result

  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [aws_security_group.aurora.id]

  serverlessv2_scaling_configuration {
    min_capacity = var.serverless_v2_min_capacity
    max_capacity = var.serverless_v2_max_capacity
  }

  backup_retention_period      = var.backup_retention_period
  preferred_backup_window      = var.preferred_backup_window
  preferred_maintenance_window = var.preferred_maintenance_window

  storage_encrypted = true
  kms_key_id        = aws_kms_key.aurora.arn

  enabled_cloudwatch_logs_exports = ["postgresql"]

  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.cluster_identifier}-final-${formatdate("YYYYMMDD-HHmmss", timestamp())}"

  apply_immediately = true

  tags = {
    Name = var.cluster_identifier
  }
}

resource "aws_rds_cluster_instance" "aurora" {
  identifier         = "${var.cluster_identifier}-instance-1"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version

  tags = {
    Name = "${var.cluster_identifier}-instance-1"
  }
}

resource "aws_kms_key" "aurora" {
  description             = "KMS key for ${var.cluster_identifier}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.cluster_identifier}-key"
  }
}

resource "aws_kms_alias" "aurora" {
  name          = "alias/${var.cluster_identifier}"
  target_key_id = aws_kms_key.aurora.key_id
}
