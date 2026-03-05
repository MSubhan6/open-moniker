variable "domain_name" {
  description = "Domain name"
  type        = string
}

variable "primary_resolver_ips" {
  description = "Primary region resolver IPs"
  type        = list(string)
  default     = []
}

variable "secondary_resolver_ips" {
  description = "Secondary region resolver IPs"
  type        = list(string)
  default     = []
}

variable "admin_load_balancer_dns" {
  description = "Admin load balancer DNS"
  type        = string
}
