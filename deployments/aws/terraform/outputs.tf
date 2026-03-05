output "primary_eks_cluster_name" {
  description = "Primary EKS cluster name"
  value       = module.eks_primary.cluster_name
}

output "primary_eks_cluster_endpoint" {
  description = "Primary EKS cluster endpoint"
  value       = module.eks_primary.cluster_endpoint
}

output "secondary_eks_cluster_name" {
  description = "Secondary EKS cluster name"
  value       = var.enable_multi_region ? module.eks_secondary.cluster_name : null
}

output "aurora_cluster_endpoint" {
  description = "Aurora cluster endpoint"
  value       = module.aurora.cluster_endpoint
}

output "aurora_reader_endpoint" {
  description = "Aurora reader endpoint"
  value       = module.aurora.reader_endpoint
}

output "resolver_dns" {
  description = "Resolver DNS endpoint"
  value       = "resolver.${var.domain_name}"
}

output "admin_dns" {
  description = "Admin dashboard DNS endpoint"
  value       = "admin.${var.domain_name}"
}

output "database_secret_arn" {
  description = "ARN of database credentials secret"
  value       = module.aurora.master_password_secret_arn
  sensitive   = true
}
