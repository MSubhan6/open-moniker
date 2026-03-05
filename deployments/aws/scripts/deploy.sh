#!/bin/bash
set -euo pipefail

# Deploy Open Moniker to AWS EKS
# Usage: ./deploy.sh <region> <environment> <aws_account_id>
#   region: us-east-1 or us-west-2
#   environment: dev, staging, or prod
#   aws_account_id: Your AWS account ID

REGION=${1:-us-east-1}
ENVIRONMENT=${2:-prod}
AWS_ACCOUNT_ID=${3:-}

if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "Error: AWS_ACCOUNT_ID is required"
    echo "Usage: $0 <region> <environment> <aws_account_id>"
    exit 1
fi

echo "===================================="
echo "Deploying Open Moniker to AWS EKS"
echo "Region: $REGION"
echo "Environment: $ENVIRONMENT"
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "===================================="

# Set kubectl context
CLUSTER_NAME="moniker-${ENVIRONMENT}-${REGION}"
echo "Setting kubectl context to $CLUSTER_NAME..."
aws eks update-kubeconfig --region "$REGION" --name "$CLUSTER_NAME"

# Get Aurora endpoints from Terraform outputs
echo "Fetching Aurora endpoints from Terraform..."
cd ../terraform
AURORA_CLUSTER_ENDPOINT=$(terraform output -raw aurora_cluster_endpoint 2>/dev/null || echo "")
AURORA_READER_ENDPOINT=$(terraform output -raw aurora_reader_endpoint 2>/dev/null || echo "")
AURORA_PASSWORD=$(aws secretsmanager get-secret-value --secret-id "moniker/${ENVIRONMENT}/telemetry/db-password" --region "$REGION" --query SecretString --output text 2>/dev/null || echo "PLACEHOLDER_PASSWORD")
cd ../scripts

if [ -z "$AURORA_CLUSTER_ENDPOINT" ]; then
    echo "Warning: Could not retrieve Aurora endpoints from Terraform. Using placeholders."
    AURORA_CLUSTER_ENDPOINT="PLACEHOLDER_CLUSTER_ENDPOINT"
    AURORA_READER_ENDPOINT="PLACEHOLDER_READER_ENDPOINT"
fi

echo "Aurora Cluster Endpoint: $AURORA_CLUSTER_ENDPOINT"
echo "Aurora Reader Endpoint: $AURORA_READER_ENDPOINT"

# Create temporary kustomization with environment variables substituted
OVERLAY_DIR="../kubernetes/overlays/${REGION}"
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo "Preparing Kubernetes manifests..."
cp -r "$OVERLAY_DIR"/* "$TEMP_DIR/"

# Substitute environment variables in patches
for file in "$TEMP_DIR"/*.yaml; do
    sed -i.bak \
        -e "s|\${AWS_ACCOUNT_ID}|${AWS_ACCOUNT_ID}|g" \
        -e "s|\${AURORA_CLUSTER_ENDPOINT}|${AURORA_CLUSTER_ENDPOINT}|g" \
        -e "s|\${AURORA_READER_ENDPOINT}|${AURORA_READER_ENDPOINT}|g" \
        -e "s|\${AURORA_PASSWORD}|${AURORA_PASSWORD}|g" \
        "$file"
    rm "${file}.bak"
done

# Build and apply with kustomize
echo "Applying Kubernetes manifests..."
kubectl apply -k "$TEMP_DIR"

# Wait for deployments to be ready
echo "Waiting for deployments to be ready..."
kubectl wait --for=condition=available --timeout=300s \
    deployment/use1-java-resolver -n moniker 2>/dev/null || \
    kubectl wait --for=condition=available --timeout=300s \
    deployment/usw2-java-resolver -n moniker || true

kubectl wait --for=condition=available --timeout=300s \
    deployment/use1-python-admin -n moniker 2>/dev/null || \
    kubectl wait --for=condition=available --timeout=300s \
    deployment/usw2-python-admin -n moniker || true

# Get service endpoints
echo ""
echo "===================================="
echo "Deployment complete!"
echo "===================================="
echo ""
echo "Java Resolver Service:"
kubectl get svc -n moniker | grep java-resolver || true
echo ""
echo "Python Admin Service:"
kubectl get svc -n moniker | grep python-admin || true
echo ""
echo "Pods:"
kubectl get pods -n moniker
echo ""
echo "To view logs:"
echo "  kubectl logs -f deployment/use1-java-resolver -n moniker"
echo "  kubectl logs -f deployment/use1-python-admin -n moniker"
echo ""
echo "To access services:"
echo "  Java Resolver: http://\$(kubectl get svc -n moniker use1-java-resolver -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
echo "  Admin Panel: http://\$(kubectl get svc -n moniker use1-python-admin -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
