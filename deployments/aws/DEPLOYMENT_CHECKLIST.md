# AWS Deployment Checklist

Use this checklist to ensure a smooth deployment of Open Moniker to AWS.

## Pre-Deployment

### ☐ AWS Account Setup
- [ ] AWS account created and accessible
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] IAM user/role has appropriate permissions:
  - EC2, EKS, RDS, Route53, VPC, CloudWatch, Secrets Manager
- [ ] AWS account ID noted: `_______________`

### ☐ Domain Configuration
- [ ] Domain name chosen: `_______________`
- [ ] Domain registrar access confirmed (if using existing domain)
- [ ] DNS delegation plan confirmed

### ☐ Local Tools
- [ ] Terraform v1.5+ installed (`terraform --version`)
- [ ] kubectl installed (`kubectl version --client`)
- [ ] kustomize installed (`kustomize version`)
- [ ] Docker installed (`docker --version`)
- [ ] jq installed (`jq --version`)
- [ ] psql client installed (for database verification)

### ☐ Repository Preparation
- [ ] Code pulled from latest main/master branch
- [ ] Java resolver builds successfully (`cd resolver-java && ./mvnw clean package`)
- [ ] Python dependencies installed (`pip install -r requirements.txt`)
- [ ] Catalog data prepared (`sample_catalog.yaml` reviewed)

## Phase 1: Infrastructure Deployment

### ☐ Terraform Configuration
- [ ] Environment chosen (dev/staging/prod): `_______________`
- [ ] `terraform/environments/<env>.tfvars` updated with:
  - [ ] `aws_account_id` (replace REPLACE_WITH_YOUR_AWS_ACCOUNT_ID)
  - [ ] `domain_name` (your actual domain)
  - [ ] `enable_secondary_region` (true for multi-region)
  - [ ] Instance types and sizes appropriate for budget
- [ ] Review cost estimates in README.md
- [ ] Budget alerts configured in AWS Billing Console

### ☐ Terraform Execution
```bash
cd deployments/aws/terraform
terraform init
terraform plan -var-file=environments/<env>.tfvars -out=tfplan
# Review plan carefully!
terraform apply tfplan
terraform output -json > outputs.json
```

- [ ] Terraform init successful
- [ ] Terraform plan reviewed (no unexpected changes)
- [ ] Terraform apply completed without errors
- [ ] VPC and subnets created
- [ ] EKS clusters operational (check AWS Console)
- [ ] Aurora cluster created and available
- [ ] Route53 hosted zone created
- [ ] NAT gateways provisioned
- [ ] Security groups configured

**Estimated time:** 20-30 minutes

### ☐ Verify Infrastructure
- [ ] EKS cluster accessible:
  ```bash
  aws eks update-kubeconfig --region us-east-1 --name moniker-<env>-us-east-1
  kubectl get nodes
  ```
- [ ] Aurora endpoint reachable (from VPC):
  ```bash
  AURORA_ENDPOINT=$(terraform output -raw aurora_cluster_endpoint)
  echo $AURORA_ENDPOINT
  ```

## Phase 2: Database Setup

### ☐ Database Migration
```bash
cd ../scripts
./migrate-db.sh <env> us-east-1
```

- [ ] Migration script executed successfully
- [ ] Tables created:
  - [ ] `access_log` (partitioned by month)
  - [ ] `hourly_stats` view
  - [ ] `daily_stats` view
- [ ] Verify with psql:
  ```bash
  PGPASSWORD=$DB_PASSWORD psql -h $AURORA_ENDPOINT -U telemetry -d moniker_telemetry -c "\dt"
  ```

## Phase 3: Container Images

### ☐ ECR Repositories
- [ ] ECR repository created for Java resolver (us-east-1)
- [ ] ECR repository created for Java resolver (us-west-2, if multi-region)
- [ ] ECR repository created for Python admin (us-east-1)
- [ ] ECR repository created for Python admin (us-west-2, if multi-region)

### ☐ Java Resolver Image
```bash
cd ../../resolver-java
./mvnw clean package -DskipTests

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1

# ECR login
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Build and push
docker build -t moniker-resolver-java -f ../deployments/render/Dockerfile.java .
docker tag moniker-resolver-java:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-resolver-java:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-resolver-java:latest
```

- [ ] Java resolver image built
- [ ] Java resolver image pushed to ECR (us-east-1)
- [ ] Java resolver image pushed to ECR (us-west-2, if multi-region)
- [ ] Image visible in AWS ECR console

### ☐ Python Admin Image
```bash
cd ../deployments/render
docker build -t moniker-admin-python -f Dockerfile.python ../..
docker tag moniker-admin-python:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-admin-python:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/moniker-admin-python:latest
```

- [ ] Python admin image built
- [ ] Python admin image pushed to ECR (us-east-1)
- [ ] Python admin image pushed to ECR (us-west-2, if multi-region)
- [ ] Image visible in AWS ECR console

## Phase 4: Kubernetes Deployment

### ☐ Pre-Deployment Configuration
- [ ] Review `kubernetes/overlays/us-east-1/*.yaml` files
- [ ] Confirm AWS_ACCOUNT_ID placeholders will be substituted
- [ ] Confirm AURORA endpoints will be substituted
- [ ] Review resource limits (adjust if needed for workload)

### ☐ Deploy to us-east-1
```bash
cd ../aws/scripts
./deploy.sh us-east-1 <env> $AWS_ACCOUNT_ID
```

- [ ] Deployment script completed without errors
- [ ] Namespace `moniker` created
- [ ] ConfigMaps created and populated
- [ ] Secrets created (database password)
- [ ] Java resolver deployment created
- [ ] Python admin deployment created
- [ ] Services created (LoadBalancer type)
- [ ] Pods running:
  ```bash
  kubectl get pods -n moniker
  ```
- [ ] All pods showing `Running` status
- [ ] No CrashLoopBackOff or Error states

### ☐ Deploy to us-west-2 (if multi-region)
```bash
./deploy.sh us-west-2 <env> $AWS_ACCOUNT_ID
```

- [ ] Repeat verification steps for us-west-2
- [ ] Pods running in both regions

**Estimated time:** 10-15 minutes per region

## Phase 5: Verification and Testing

### ☐ Health Checks
```bash
./health-check.sh us-east-1
# If multi-region:
./health-check.sh us-west-2
```

- [ ] Java resolver health check: ✅
- [ ] Python admin health check: ✅
- [ ] Database connectivity test: ✅
- [ ] All pods healthy
- [ ] No error events in namespace

### ☐ Service Endpoints
- [ ] Get Java resolver endpoint:
  ```bash
  kubectl get svc -n moniker | grep java-resolver
  ```
  Resolver LB: `_______________`

- [ ] Get Python admin endpoint:
  ```bash
  kubectl get svc -n moniker | grep python-admin
  ```
  Admin LB: `_______________`

### ☐ Functional Testing
- [ ] Test resolver health endpoint:
  ```bash
  curl http://<resolver-lb>/health
  ```
  Expected: `{"status":"healthy",...}`

- [ ] Test admin health endpoint:
  ```bash
  curl http://<admin-lb>/health
  ```
  Expected: `{"status":"healthy",...}`

- [ ] Test resolution (will fail if catalog not loaded, OK):
  ```bash
  curl http://<resolver-lb>/resolve/test/path@latest
  ```

- [ ] Access admin dashboard in browser:
  ```
  http://<admin-lb>/dashboard
  ```
  - [ ] Dashboard loads
  - [ ] Live telemetry section visible
  - [ ] WebSocket connects (status indicator: 🟢)

### ☐ Telemetry Verification
- [ ] Generate test traffic:
  ```bash
  for i in {1..100}; do
    curl -s http://<resolver-lb>/health > /dev/null
  done
  ```

- [ ] Check database for events:
  ```bash
  PGPASSWORD=$DB_PASSWORD psql -h $AURORA_ENDPOINT -U telemetry -d moniker_telemetry \
    -c "SELECT COUNT(*) FROM access_log WHERE timestamp > NOW() - INTERVAL '5 minutes';"
  ```
  Expected: > 0 events

- [ ] Check dashboard updates:
  - [ ] Open dashboard in browser
  - [ ] Generate more traffic
  - [ ] Confirm RPS chart updates within 2-3 seconds
  - [ ] Confirm latency chart shows data

## Phase 6: DNS Configuration

### ☐ Route 53 Setup
- [ ] Get all resolver Load Balancer IPs/hostnames:
  ```bash
  # us-east-1
  kubectl get svc -n moniker use1-java-resolver -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

  # us-west-2 (if multi-region)
  kubectl get svc -n moniker usw2-java-resolver -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
  ```

- [ ] Create DNS records (manually or via Terraform DNS module):
  - [ ] `resolver.<domain>` → Weighted A/ALIAS records to all resolver LBs
  - [ ] `admin.<domain>` → CNAME to admin LB (us-east-1)

- [ ] Test DNS resolution:
  ```bash
  dig resolver.<your-domain>
  nslookup admin.<your-domain>
  ```

- [ ] Test via DNS names:
  ```bash
  curl http://resolver.<your-domain>/health
  curl http://admin.<your-domain>/health
  ```

## Phase 7: Production Readiness

### ☐ Monitoring
- [ ] CloudWatch Logs groups created:
  - [ ] `/aws/eks/moniker-<env>-us-east-1/cluster`
  - [ ] `/aws/rds/cluster/moniker-telemetry/postgresql`
- [ ] CloudWatch metrics visible for EKS nodes
- [ ] Aurora performance metrics visible
- [ ] Set up CloudWatch Alarms for:
  - [ ] High CPU usage (EKS nodes)
  - [ ] High memory usage
  - [ ] Aurora ACU usage
  - [ ] Pod restart count
  - [ ] Failed health checks

### ☐ Security
- [ ] Security groups reviewed (least privilege)
- [ ] IAM roles have minimal permissions
- [ ] Secrets stored in Secrets Manager (not hardcoded)
- [ ] Encryption at rest enabled (EBS, Aurora)
- [ ] VPC flow logs enabled (optional)
- [ ] Consider: WAF, Shield for DDoS protection

### ☐ Cost Management
- [ ] AWS Budget alert configured
- [ ] Cost Explorer reviewed
- [ ] Tag compliance checked (all resources tagged)
- [ ] Spot instances considered (if not prod)
- [ ] Right-sizing reviewed (over/under provisioned?)

### ☐ Backup and DR
- [ ] Aurora automated backups confirmed (7 days)
- [ ] Test Aurora snapshot restore procedure
- [ ] Document failover procedure (primary → secondary region)
- [ ] Test cross-region failover (if multi-region)

### ☐ Documentation
- [ ] Update internal runbook with:
  - [ ] Deployment procedure (this checklist)
  - [ ] Rollback procedure
  - [ ] Troubleshooting guide
  - [ ] On-call contact information
- [ ] Share dashboard URL with team
- [ ] Share resolver endpoints with API consumers

## Post-Deployment

### ☐ Load Testing
- [ ] Install load testing tool (`hey`, `ab`, `k6`)
- [ ] Run sustained load test:
  ```bash
  hey -z 60s -c 100 http://resolver.<your-domain>/resolve/test/path@latest
  ```
- [ ] Monitor dashboard during load test
- [ ] Verify resolvers handle expected RPS
- [ ] Check Aurora auto-scaling (ACU should increase under load)
- [ ] Confirm no errors or pod restarts

### ☐ Performance Tuning
- [ ] Review telemetry batch size (increase if high volume)
- [ ] Review flush interval (decrease for lower latency)
- [ ] Tune JVM heap sizes if needed
- [ ] Adjust pod resource limits based on actual usage
- [ ] Consider HPA (Horizontal Pod Autoscaler) for resolvers

### ☐ Operational Procedures
- [ ] Document deployment updates procedure
- [ ] Document scaling procedure
- [ ] Document rollback procedure
- [ ] Schedule regular review of costs and performance
- [ ] Set up alerting for on-call team

## Rollback Plan

If issues arise post-deployment:

### ☐ Application Rollback
```bash
# Rollback to previous deployment
kubectl rollout undo deployment/use1-java-resolver -n moniker
kubectl rollout undo deployment/use1-python-admin -n moniker

# Or rollback to specific revision
kubectl rollout history deployment/use1-java-resolver -n moniker
kubectl rollout undo deployment/use1-java-resolver --to-revision=<N> -n moniker
```

### ☐ Infrastructure Rollback
```bash
cd deployments/aws/terraform
# Restore from previous state backup
terraform state pull > backup.tfstate
# Or use versioned state if S3 backend configured
terraform state pull -state=s3://bucket/path/terraform.tfstate.d/<version>
```

### ☐ Emergency Shutdown
```bash
# Scale down to 0 replicas (preserves config)
kubectl scale deployment --all --replicas=0 -n moniker

# Or delete namespace entirely
kubectl delete namespace moniker
```

## Success Criteria

Deployment is successful when:

- [x] All pods in `Running` state
- [x] Health checks return 200 OK
- [x] Telemetry events flowing to Aurora
- [x] Dashboard shows live data with 2s updates
- [x] Load test achieves target RPS (6,000+ with 6 resolvers)
- [x] No errors in logs for 10+ minutes
- [x] Aurora scaling working (ACU adjusts to load)
- [x] DNS resolution working
- [x] Cross-region failover tested (if multi-region)

## Notes

Use this space for deployment-specific notes:

- Deployment date: `_______________`
- Deployed by: `_______________`
- Environment: `_______________`
- Issues encountered: `_______________`
- Resolution: `_______________`
