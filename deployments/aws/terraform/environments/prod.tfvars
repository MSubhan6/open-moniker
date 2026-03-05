# Production Environment Configuration

environment      = "prod"
project_name     = "moniker"
aws_account_id   = "REPLACE_WITH_YOUR_AWS_ACCOUNT_ID"

# Primary region (us-east-1)
primary_region   = "us-east-1"
primary_vpc_cidr = "10.20.0.0/16"

# Secondary region (us-west-2) - Full multi-region for prod
secondary_region   = "us-west-2"
secondary_vpc_cidr = "10.21.0.0/16"
enable_secondary_region = true

# Domain for Route 53
domain_name = "moniker.example.com"

# Aurora configuration - Full capacity for production
aurora_min_capacity = 0.5  # ACU
aurora_max_capacity = 4    # ACU
aurora_backup_retention_period = 7  # 7 days retention

# Enable cross-region Aurora Global Database
enable_global_database = true

# EKS configuration - Production scale
eks_cluster_version = "1.28"

# Resolver nodes - 3 per region across 3 AZs
resolver_node_instance_type = "t3.medium"
resolver_node_min_size = 3
resolver_node_max_size = 10  # Allow scaling under load
resolver_node_desired_size = 3

# Admin nodes - 1 per region
admin_node_instance_type = "t3.small"
admin_node_min_size = 1
admin_node_max_size = 2
admin_node_desired_size = 1

# Use On-Demand instances for production reliability
use_spot_instances = false

# Enable enhanced monitoring
enable_container_insights = true
enable_cloudwatch_logs = true

# Security
enable_encryption_at_rest = true
enable_encryption_in_transit = true

# Backup and DR
enable_automated_backups = true
backup_window = "03:00-04:00"  # UTC
maintenance_window = "sun:04:00-sun:05:00"  # UTC

# Tags
tags = {
  Environment = "production"
  Project     = "moniker"
  ManagedBy   = "terraform"
  Owner       = "ops-team"
  CostCenter  = "infrastructure"
}
