output "zone_id" {
  description = "Route53 zone ID"
  value       = aws_route53_zone.main.zone_id
}

output "name_servers" {
  description = "Route53 name servers"
  value       = aws_route53_zone.main.name_servers
}

output "resolver_fqdn" {
  description = "Resolver FQDN"
  value       = "resolver.${var.domain_name}"
}

output "admin_fqdn" {
  description = "Admin FQDN"
  value       = "admin.${var.domain_name}"
}
