resource "aws_route53_zone" "main" {
  name = var.domain_name

  tags = {
    Name = var.domain_name
  }
}

# Resolver DNS - round-robin weighted records
resource "aws_route53_record" "resolver" {
  count = length(var.primary_resolver_ips) + length(var.secondary_resolver_ips)

  zone_id = aws_route53_zone.main.zone_id
  name    = "resolver.${var.domain_name}"
  type    = "A"
  ttl     = 60

  records = [
    count.index < length(var.primary_resolver_ips) ?
      var.primary_resolver_ips[count.index] :
      var.secondary_resolver_ips[count.index - length(var.primary_resolver_ips)]
  ]

  set_identifier = "resolver-${count.index + 1}"

  weighted_routing_policy {
    weight = 100
  }
}

# Admin DNS - CNAME to load balancer
resource "aws_route53_record" "admin" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "admin.${var.domain_name}"
  type    = "CNAME"
  ttl     = 300

  records = [var.admin_load_balancer_dns]
}

# Health checks for resolvers
resource "aws_route53_health_check" "resolver" {
  count = length(var.primary_resolver_ips)

  ip_address        = var.primary_resolver_ips[count.index]
  port              = 80
  type              = "HTTP"
  resource_path     = "/health"
  failure_threshold = 3
  request_interval  = 30

  tags = {
    Name = "resolver-${count.index + 1}-health"
  }
}
