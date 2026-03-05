# Development Environment Configuration

environment      = "dev"
project_name     = "moniker"
aws_account_id   = "REPLACE_WITH_YOUR_AWS_ACCOUNT_ID"

# Primary region (us-east-1)
primary_region   = "us-east-1"
primary_vpc_cidr = "10.0.0.0/16"

# Secondary region (us-west-2) - Disabled for dev to save costs
secondary_region   = "us-west-2"
secondary_vpc_cidr = "10.1.0.0/16"
enable_secondary_region = false  # Set to true for multi-region testing

# Domain for Route 53
domain_name = "dev.moniker.example.com"

# Aurora configuration - Minimal for dev
aurora_min_capacity = 0.5  # ACU
aurora_max_capacity = 1    # ACU (lower for dev)
aurora_backup_retention_period = 1  # Only 1 day for dev

# EKS configuration - Smaller instances for dev
eks_cluster_version = "1.28"
resolver_node_instance_type = "t3.small"   # Smaller for dev
resolver_node_min_size = 1
resolver_node_max_size = 3
resolver_node_desired_size = 1

admin_node_instance_type = "t3.micro"      # Minimal for dev
admin_node_min_size = 1
admin_node_max_size = 1
admin_node_desired_size = 1

# Use Spot instances for cost savings
use_spot_instances = true

# Tags
tags = {
  Environment = "development"
  Project     = "moniker"
  ManagedBy   = "terraform"
  Owner       = "dev-team"
}
