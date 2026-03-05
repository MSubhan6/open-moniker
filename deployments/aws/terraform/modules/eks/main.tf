module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = var.cluster_name
  cluster_version = var.kubernetes_version

  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  # Cluster endpoint access
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  # Cluster encryption
  cluster_encryption_config = {
    resources        = ["secrets"]
    provider_key_arn = aws_kms_key.eks.arn
  }

  # Managed node groups
  eks_managed_node_groups = {
    resolvers = {
      name = "${var.cluster_name}-resolvers"

      desired_size = var.resolver_node_group.desired_size
      min_size     = var.resolver_node_group.min_size
      max_size     = var.resolver_node_group.max_size

      instance_types = var.resolver_node_group.instance_types
      capacity_type  = "ON_DEMAND"

      labels = {
        role = "resolver"
      }

      taints = []

      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 50
            volume_type           = "gp3"
            encrypted             = true
            kms_key_id            = aws_kms_key.eks.arn
            delete_on_termination = true
          }
        }
      }
    }

    admin = {
      name = "${var.cluster_name}-admin"

      desired_size = var.admin_node_group.desired_size
      min_size     = var.admin_node_group.min_size
      max_size     = var.admin_node_group.max_size

      instance_types = var.admin_node_group.instance_types
      capacity_type  = "ON_DEMAND"

      labels = {
        role = "admin"
      }

      taints = []

      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 20
            volume_type           = "gp3"
            encrypted             = true
            kms_key_id            = aws_kms_key.eks.arn
            delete_on_termination = true
          }
        }
      }
    }
  }

  # Add-ons
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent = true
    }
  }

  # IRSA for pods
  enable_irsa = true

  tags = {
    Environment = "production"
  }
}

# KMS key for EKS encryption
resource "aws_kms_key" "eks" {
  description             = "EKS cluster ${var.cluster_name} encryption key"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.cluster_name}-eks-key"
  }
}

resource "aws_kms_alias" "eks" {
  name          = "alias/${var.cluster_name}-eks"
  target_key_id = aws_kms_key.eks.key_id
}

# Security group for EKS cluster
resource "aws_security_group_rule" "cluster_to_node" {
  description              = "Allow cluster to communicate with nodes"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "-1"
  security_group_id        = module.eks.cluster_security_group_id
  source_security_group_id = module.eks.node_security_group_id
  type                     = "egress"
}
