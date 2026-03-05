terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
  }

  backend "s3" {
    bucket         = "moniker-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "moniker-terraform-locks"
  }
}

provider "aws" {
  region = var.primary_region

  default_tags {
    tags = {
      Project     = "open-moniker"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

provider "aws" {
  alias  = "secondary"
  region = var.secondary_region

  default_tags {
    tags = {
      Project     = "open-moniker"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Primary region VPC and EKS
module "vpc_primary" {
  source = "./modules/vpc"

  name               = "moniker-${var.environment}-primary"
  region             = var.primary_region
  vpc_cidr           = var.primary_vpc_cidr
  availability_zones = data.aws_availability_zones.primary.names
}

module "eks_primary" {
  source = "./modules/eks"

  cluster_name       = "moniker-${var.environment}-${var.primary_region}"
  vpc_id             = module.vpc_primary.vpc_id
  private_subnet_ids = module.vpc_primary.private_subnet_ids
  kubernetes_version = var.kubernetes_version

  resolver_node_group = {
    desired_size = var.resolver_instances_per_region
    min_size     = var.resolver_instances_per_region
    max_size     = var.resolver_instances_per_region * 2
    instance_types = ["t3.medium"]
  }

  admin_node_group = {
    desired_size = 1
    min_size     = 1
    max_size     = 2
    instance_types = ["t3.small"]
  }
}

# Secondary region VPC and EKS
module "vpc_secondary" {
  source = "./modules/vpc"
  providers = {
    aws = aws.secondary
  }

  name               = "moniker-${var.environment}-secondary"
  region             = var.secondary_region
  vpc_cidr           = var.secondary_vpc_cidr
  availability_zones = data.aws_availability_zones.secondary.names
}

module "eks_secondary" {
  source = "./modules/eks"
  providers = {
    aws = aws.secondary
  }

  cluster_name       = "moniker-${var.environment}-${var.secondary_region}"
  vpc_id             = module.vpc_secondary.vpc_id
  private_subnet_ids = module.vpc_secondary.private_subnet_ids
  kubernetes_version = var.kubernetes_version

  resolver_node_group = {
    desired_size = var.resolver_instances_per_region
    min_size     = var.resolver_instances_per_region
    max_size     = var.resolver_instances_per_region * 2
    instance_types = ["t3.medium"]
  }

  admin_node_group = {
    desired_size = 0
    min_size     = 0
    max_size     = 1
    instance_types = ["t3.small"]
  }
}

# Aurora Serverless v2 (primary region)
module "aurora" {
  source = "./modules/aurora"

  cluster_identifier = "moniker-${var.environment}-telemetry"
  database_name      = "moniker_telemetry"
  master_username    = "postgres"

  vpc_id                 = module.vpc_primary.vpc_id
  private_subnet_ids     = module.vpc_primary.private_subnet_ids
  allowed_security_groups = [
    module.eks_primary.cluster_security_group_id,
    module.eks_secondary.cluster_security_group_id
  ]

  serverless_v2_min_capacity = var.aurora_min_capacity
  serverless_v2_max_capacity = var.aurora_max_capacity

  backup_retention_period = 7
  preferred_backup_window = "03:00-04:00"

  enable_global_database = var.enable_multi_region
}

# Route53 DNS
module "dns" {
  source = "./modules/dns"

  domain_name = var.domain_name

  primary_resolver_ips = module.eks_primary.resolver_load_balancer_ips
  secondary_resolver_ips = var.enable_multi_region ? module.eks_secondary.resolver_load_balancer_ips : []

  admin_load_balancer_dns = module.eks_primary.admin_load_balancer_dns
}

# Data sources
data "aws_availability_zones" "primary" {
  state = "available"
}

data "aws_availability_zones" "secondary" {
  provider = aws.secondary
  state    = "available"
}
