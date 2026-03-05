# AWS Production Deployment

This directory contains all infrastructure and deployment configuration for running Open Moniker on AWS with EKS, Aurora Serverless v2, and multi-region support.

## Architecture Overview

- **6 Java resolvers** (3 in us-east-1, 3 in us-west-2) for high-throughput resolution
- **2 Python admin instances** (1 per region) for configuration management and live telemetry dashboard
- **Aurora PostgreSQL Serverless v2** (us-east-1 primary, us-west-2 read replica) for telemetry storage
- **Route 53 weighted round-robin DNS** distributing traffic across all 6 resolvers
- **EKS clusters** (1 per region) with multi-AZ deployment

## Directory Structure

```
aws/
├── terraform/                    # Infrastructure as Code
│   ├── main.tf                   # Root module
│   ├── variables.tf              # Input variables
│   ├── outputs.tf                # Outputs
│   ├── modules/
│   │   ├── vpc/                  # VPC, subnets, NAT gateways
│   │   ├── eks/                  # EKS cluster + node groups
│   │   ├── aurora/               # Aurora Serverless v2
│   │   └── dns/                  # Route 53 round-robin
│   └── environments/
│       ├── dev.tfvars            # Dev environment
│       ├── staging.tfvars        # Staging
│       └── prod.tfvars           # Production
├── kubernetes/                   # K8s manifests
│   ├── base/                     # Base configs (Kustomize)
│   │   ├── java-resolver.yaml
│   │   ├── python-admin.yaml
│   │   ├── configmap.yaml
│   │   ├── secrets.yaml
│   │   └── kustomization.yaml
│   └── overlays/
│       ├── us-east-1/            # us-east-1 specific configs
│       └── us-west-2/            # us-west-2 specific configs
├── docker/                       # Dockerfiles
│   ├── Dockerfile.java           # Java resolver
│   └── Dockerfile.python         # Python admin
├── scripts/                      # Helper scripts
│   ├── deploy.sh                 # Deploy to EKS
│   ├── migrate-db.sh             # Run DB migrations
│   └── health-check.sh           # Smoke tests
└── README.md                     # This file
```

## Prerequisites

1. **AWS CLI** configured with credentials
   ```bash
   aws configure
   ```

2. **Terraform** (v1.5+)
   ```bash
   terraform --version
   ```

3. **kubectl** and **kustomize**
   ```bash
   kubectl version --client
   kustomize version
   ```

4. **Docker** (for building images)
   ```bash
   docker --version
   ```

5. **jq** (for scripts)
   ```bash
   jq --version
   ```

## Step 1: Deploy Infrastructure with Terraform

### 1.1. Configure Environment

Create `terraform/environments/prod.tfvars`:

```hcl
environment      = "prod"
project_name     = "moniker"
aws_account_id   = "123456789012"  # Replace with your AWS account ID

# Primary region (us-east-1)
primary_region   = "us-east-1"
primary_vpc_cidr = "10.0.0.0/16"

# Secondary region (us-west-2)
secondary_region   = "us-west-2"
secondary_vpc_cidr = "10.1.0.0/16"

# Domain for Route 53
domain_name = "moniker.example.com"

# Aurora configuration
aurora_min_capacity = 0.5  # ACU
aurora_max_capacity = 4    # ACU
aurora_backup_retention_period = 7

# EKS configuration
eks_cluster_version = "1.28"
resolver_node_instance_type = "t3.medium"
admin_node_instance_type = "t3.small"

# Tags
tags = {
  Environment = "production"
  Project     = "moniker"
  ManagedBy   = "terraform"
}
```

### 1.2. Initialize and Deploy

```bash
cd terraform

# Initialize Terraform
terraform init

# Plan deployment
terraform plan -var-file=environments/prod.tfvars -out=tfplan

# Review the plan, then apply
terraform apply tfplan

# Save outputs
terraform output -json > outputs.json
```

This will create:
- 2 VPCs (us-east-1, us-west-2) with 3 public + 3 private subnets each
- 2 EKS clusters
- 1 Aurora Serverless v2 cluster with global database
- Route 53 hosted zone
- Security groups, IAM roles, NAT gateways, etc.

**Estimated time:** 20-30 minutes

## Step 2: Run Database Migrations

Once Aurora is up, run the schema migration:

```bash
cd ../scripts
./migrate-db.sh prod us-east-1
```

This will:
- Retrieve Aurora endpoint from Terraform outputs
- Get database password from AWS Secrets Manager
- Run `schema.sql` (from resolver-go implementation)
- Create partitioned tables, views, indexes

## Step 3: Build and Push Docker Images

### 3.1. Build Java Resolver

```bash
cd ../../resolver-java

# Build JAR
./mvnw clean package -DskipTests

# Get ECR login
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Create ECR repository if not exists
aws ecr create-repository --repository-name moniker-resolver-java --region $AWS_REGION || true

# Build and push
docker build -t moniker-resolver-java -f ../deployments/render/Dockerfile.java .
docker tag moniker-resolver-java:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-resolver-java:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-resolver-java:latest

# Repeat for us-west-2
AWS_REGION=us-west-2
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
aws ecr create-repository --repository-name moniker-resolver-java --region $AWS_REGION || true
docker tag moniker-resolver-java:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-resolver-java:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-resolver-java:latest
```

### 3.2. Build Python Admin

```bash
cd ../deployments/render

# Build
docker build -t moniker-admin-python -f Dockerfile.python ../..

# Push to us-east-1
AWS_REGION=us-east-1
aws ecr create-repository --repository-name moniker-admin-python --region $AWS_REGION || true
docker tag moniker-admin-python:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-admin-python:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-admin-python:latest

# Push to us-west-2
AWS_REGION=us-west-2
aws ecr create-repository --repository-name moniker-admin-python --region $AWS_REGION || true
docker tag moniker-admin-python:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-admin-python:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-admin-python:latest
```

## Step 4: Deploy to EKS

### 4.1. Deploy to us-east-1

```bash
cd ../aws/scripts
./deploy.sh us-east-1 prod $AWS_ACCOUNT_ID
```

This will:
- Update kubectl context to us-east-1 EKS cluster
- Fetch Aurora endpoints from Terraform
- Apply Kubernetes manifests with Kustomize
- Wait for deployments to be ready
- Display service endpoints

### 4.2. Deploy to us-west-2

```bash
./deploy.sh us-west-2 prod $AWS_ACCOUNT_ID
```

## Step 5: Verify Deployment

Run health checks:

```bash
./health-check.sh us-east-1
./health-check.sh us-west-2
```

This will:
- Test health endpoints for both Java and Python services
- Verify database connectivity
- Check pod status
- Display service URLs

## Step 6: Configure DNS

Get the Load Balancer endpoints:

```bash
# us-east-1 resolvers
kubectl get svc -n moniker --context=moniker-prod-us-east-1 | grep java-resolver

# us-west-2 resolvers
kubectl get svc -n moniker --context=moniker-prod-us-west-2 | grep java-resolver
```

Update Route 53 (or use Terraform DNS module) to create weighted records:
- `resolver.moniker.example.com` → 6 A records (weight 100 each)
- `admin.moniker.example.com` → CNAME to us-east-1 admin LB

## Accessing Services

Once deployed:

- **Java Resolvers:** `http://resolver.moniker.example.com/resolve/domain/path@version`
- **Admin Dashboard:** `http://admin.moniker.example.com/dashboard`
- **Config UI:** `http://admin.moniker.example.com/`

## Monitoring

### View Logs

```bash
# Resolver logs
kubectl logs -f -n moniker -l app=moniker-resolver --context=moniker-prod-us-east-1

# Admin logs
kubectl logs -f -n moniker -l app=moniker-admin --context=moniker-prod-us-east-1
```

### Live Telemetry Dashboard

1. Open `http://admin.moniker.example.com/dashboard`
2. You'll see real-time charts showing:
   - Requests per second for each resolver
   - P95 latency per resolver
   - Error rates
   - Health status

### CloudWatch

Terraform automatically creates CloudWatch log groups:
- `/aws/eks/moniker-prod-us-east-1/cluster`
- `/aws/rds/cluster/moniker-telemetry/postgresql`

## Cost Optimization

### Current Estimated Monthly Cost (~$1,000)

- EKS Control Plane (2 regions): $144
- EC2 Nodes (6 t3.medium + 2 t3.small): $150
- Aurora Serverless v2 (avg 1.5 ACU): $260
- NAT Gateways (6 total): $194
- Load Balancers (4 NLBs): $64
- Data Transfer: $40
- CloudWatch: $15
- Route 53: $1
- Secrets Manager: $2

### Optimization Options

1. **Use Spot Instances** for EKS nodes: -50% ($500/month savings)
   ```hcl
   capacity_type = "SPOT"
   ```

2. **Single Region Only:** -50% ($500/month savings)
   - Deploy only to us-east-1
   - Remove us-west-2 from Terraform

3. **Smaller Aurora:** Use min/max 0.5 ACU: -$100/month
   ```hcl
   aurora_min_capacity = 0.5
   aurora_max_capacity = 1
   ```

4. **Fewer Resolvers:** 3 instead of 6: -$75/month
   - Change replicas in overlays to 1 or 2

5. **Use ARM Graviton (t4g.medium):** -20% ($200/month savings)
   ```hcl
   resolver_node_instance_type = "t4g.medium"
   ```

**Recommended production budget:** $600-800/month with optimizations

## Scaling

### Horizontal Pod Autoscaling

Add HPA for resolvers:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: java-resolver-hpa
  namespace: moniker
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: use1-java-resolver
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Cluster Autoscaling

EKS Cluster Autoscaler is configured in Terraform to scale node groups based on pending pods.

## Disaster Recovery

### Backup Strategy

- **Aurora:** Automated daily backups (7-day retention)
- **Config Files:** Stored in EBS volumes with automated snapshots
- **Container Images:** Stored in ECR with lifecycle policies

### Failover Procedure

If us-east-1 fails:

1. Traffic automatically routes to us-west-2 (Route 53 weighted DNS)
2. Resolvers in us-west-2 continue serving with Aurora read replica
3. Promote us-west-2 Aurora replica to primary:
   ```bash
   aws rds failover-global-cluster \
       --global-cluster-identifier moniker-global \
       --target-db-cluster-identifier moniker-telemetry-us-west-2
   ```
4. Update admin service to point to new primary

## Troubleshooting

### Pods not starting

```bash
kubectl describe pod <pod-name> -n moniker
kubectl logs <pod-name> -n moniker
```

Common issues:
- Image pull errors: Check ECR permissions
- Database connection errors: Verify security groups
- Memory limits: Increase resource requests

### Aurora connection timeouts

Check security groups:
```bash
aws ec2 describe-security-groups --group-ids <aurora-sg-id>
```

Ensure EKS node security group is allowed to connect to Aurora on port 5432.

### High latency

1. Check Aurora scaling:
   ```bash
   aws rds describe-db-clusters --db-cluster-identifier moniker-telemetry
   ```

2. Check telemetry batch size (may need tuning):
   ```yaml
   moniker:
     telemetry:
       batch-size: 100  # Increase if high volume
       flush-interval-seconds: 5.0  # Decrease for lower latency
   ```

## Updating Deployments

### Update Application Code

1. Build new Docker images with updated code
2. Push to ECR with new tag (e.g., `v1.2.0`)
3. Update image tag in Kustomize overlays
4. Apply:
   ```bash
   ./deploy.sh us-east-1 prod $AWS_ACCOUNT_ID
   ```

### Rolling Back

```bash
kubectl rollout undo deployment/use1-java-resolver -n moniker
kubectl rollout status deployment/use1-java-resolver -n moniker
```

### Update Infrastructure

1. Modify Terraform files
2. Plan and apply:
   ```bash
   terraform plan -var-file=environments/prod.tfvars
   terraform apply
   ```

## Cleanup

To destroy all resources:

```bash
# Delete Kubernetes resources first
kubectl delete namespace moniker --context=moniker-prod-us-east-1
kubectl delete namespace moniker --context=moniker-prod-us-west-2

# Destroy Terraform infrastructure
cd terraform
terraform destroy -var-file=environments/prod.tfvars
```

**Warning:** This will delete all data including Aurora databases. Make sure to backup first.

## Support

For issues or questions:
- Check logs: `kubectl logs -f -n moniker -l app=moniker-resolver`
- Review events: `kubectl get events -n moniker --sort-by='.lastTimestamp'`
- CloudWatch Logs: AWS Console → CloudWatch → Log Groups
- GitHub Issues: https://github.com/ganizanisitara/open-moniker-svc/issues

## Next Steps

1. **Set up CI/CD:** GitHub Actions for automated deployments
2. **Add monitoring:** Prometheus + Grafana for detailed metrics
3. **Implement alerts:** CloudWatch Alarms for critical issues
4. **Configure WAF:** AWS WAF for DDoS protection
5. **Enable encryption:** TLS/SSL certificates with ACM
6. **Add caching:** CloudFront CDN for static assets
7. **Implement rate limiting:** API Gateway or custom middleware
