# Staging Environment Configuration

environment      = "staging"
project_name     = "moniker"
aws_account_id   = "REPLACE_WITH_YOUR_AWS_ACCOUNT_ID"

# Primary region (us-east-1)
primary_region   = "us-east-1"
primary_vpc_cidr = "10.10.0.0/16"

# Secondary region (us-west-2) - Optional for staging
secondary_region   = "us-west-2"
secondary_vpc_cidr = "10.11.0.0/16"
enable_secondary_region = false  # Set to true for full multi-region testing

# Domain for Route 53
domain_name = "staging.moniker.example.com"

# Aurora configuration - Moderate capacity for staging
aurora_min_capacity = 0.5  # ACU
aurora_max_capacity = 2    # ACU
aurora_backup_retention_period = 3  # 3 days for staging

# EKS configuration - Production-like but smaller
eks_cluster_version = "1.28"
resolver_node_instance_type = "t3.medium"
resolver_node_min_size = 2
resolver_node_max_size = 4
resolver_node_desired_size = 2

admin_node_instance_type = "t3.small"
admin_node_min_size = 1
admin_node_max_size = 2
admin_node_desired_size = 1

# Mix of On-Demand and Spot for reliability testing
use_spot_instances = true

# Tags
tags = {
  Environment = "staging"
  Project     = "moniker"
  ManagedBy   = "terraform"
  Owner       = "qa-team"
}
