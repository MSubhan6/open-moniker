variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs"
  type        = list(string)
}

variable "resolver_node_group" {
  description = "Resolver node group configuration"
  type = object({
    desired_size   = number
    min_size       = number
    max_size       = number
    instance_types = list(string)
  })
}

variable "admin_node_group" {
  description = "Admin node group configuration"
  type = object({
    desired_size   = number
    min_size       = number
    max_size       = number
    instance_types = list(string)
  })
}
