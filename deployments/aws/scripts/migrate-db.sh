#!/bin/bash
set -euo pipefail

# Run database migrations for Open Moniker telemetry database
# Usage: ./migrate-db.sh <environment> <region>
#   environment: dev, staging, or prod
#   region: us-east-1 or us-west-2

ENVIRONMENT=${1:-prod}
REGION=${2:-us-east-1}

echo "===================================="
echo "Running Database Migrations"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo "===================================="

# Get Aurora endpoint and password
cd ../terraform
AURORA_ENDPOINT=$(terraform output -raw aurora_cluster_endpoint 2>/dev/null || echo "")
cd ../scripts

if [ -z "$AURORA_ENDPOINT" ]; then
    echo "Error: Could not retrieve Aurora endpoint from Terraform"
    exit 1
fi

# Get password from Secrets Manager
echo "Retrieving database password from AWS Secrets Manager..."
DB_PASSWORD=$(aws secretsmanager get-secret-value \
    --secret-id "moniker/${ENVIRONMENT}/telemetry/db-password" \
    --region "$REGION" \
    --query SecretString \
    --output text)

if [ -z "$DB_PASSWORD" ]; then
    echo "Error: Could not retrieve database password"
    exit 1
fi

# Schema file location (from resolver-go implementation)
SCHEMA_FILE="../../resolver-go/schema.sql"

if [ ! -f "$SCHEMA_FILE" ]; then
    echo "Error: Schema file not found at $SCHEMA_FILE"
    exit 1
fi

echo "Database endpoint: $AURORA_ENDPOINT"
echo "Running migrations..."

# Run the schema SQL
PGPASSWORD="$DB_PASSWORD" psql \
    -h "$AURORA_ENDPOINT" \
    -U telemetry \
    -d moniker_telemetry \
    -f "$SCHEMA_FILE" \
    --echo-errors \
    --set ON_ERROR_STOP=1

echo ""
echo "Migration complete!"
echo ""

# Show table info
echo "Verifying tables..."
PGPASSWORD="$DB_PASSWORD" psql \
    -h "$AURORA_ENDPOINT" \
    -U telemetry \
    -d moniker_telemetry \
    -c "\dt" \
    -c "SELECT COUNT(*) FROM access_log;" \
    --echo-queries

echo ""
echo "Database is ready!"
