#!/bin/bash
set -euo pipefail

# Health check and smoke tests for Open Moniker EKS deployment
# Usage: ./health-check.sh <region>

REGION=${1:-us-east-1}

echo "===================================="
echo "Open Moniker Health Check"
echo "Region: $REGION"
echo "===================================="
echo ""

# Get service endpoints
echo "Fetching service endpoints..."
RESOLVER_LB=$(kubectl get svc -n moniker -o json | jq -r '.items[] | select(.metadata.name | contains("java-resolver")) | .status.loadBalancer.ingress[0].hostname' | head -1)
ADMIN_LB=$(kubectl get svc -n moniker -o json | jq -r '.items[] | select(.metadata.name | contains("python-admin")) | .status.loadBalancer.ingress[0].hostname' | head -1)

if [ -z "$RESOLVER_LB" ] || [ "$RESOLVER_LB" == "null" ]; then
    echo "Error: Could not find Java Resolver load balancer"
    echo "Services:"
    kubectl get svc -n moniker
    exit 1
fi

if [ -z "$ADMIN_LB" ] || [ "$ADMIN_LB" == "null" ]; then
    echo "Error: Could not find Python Admin load balancer"
    echo "Services:"
    kubectl get svc -n moniker
    exit 1
fi

echo "Java Resolver LB: $RESOLVER_LB"
echo "Python Admin LB: $ADMIN_LB"
echo ""

# Test resolver health endpoint
echo "Testing Java Resolver health endpoint..."
RESOLVER_HEALTH=$(curl -s -f "http://${RESOLVER_LB}/health" || echo "FAILED")
if [ "$RESOLVER_HEALTH" == "FAILED" ]; then
    echo "❌ Java Resolver health check FAILED"
    exit 1
else
    echo "✅ Java Resolver is healthy"
    echo "$RESOLVER_HEALTH" | jq '.'
fi
echo ""

# Test admin health endpoint
echo "Testing Python Admin health endpoint..."
ADMIN_HEALTH=$(curl -s -f "http://${ADMIN_LB}/health" || echo "FAILED")
if [ "$ADMIN_HEALTH" == "FAILED" ]; then
    echo "❌ Python Admin health check FAILED"
    exit 1
else
    echo "✅ Python Admin is healthy"
    echo "$ADMIN_HEALTH" | jq '.'
fi
echo ""

# Test resolver functionality
echo "Testing resolver functionality..."
RESOLVE_RESULT=$(curl -s -f "http://${RESOLVER_LB}/resolve/test/path@latest" || echo "FAILED")
if [ "$RESOLVE_RESULT" == "FAILED" ]; then
    echo "⚠️  Resolver test failed (this is expected if catalog not populated)"
else
    echo "✅ Resolver is responding"
    echo "$RESOLVE_RESULT" | jq '.' | head -20
fi
echo ""

# Check pod status
echo "Pod Status:"
kubectl get pods -n moniker -o wide
echo ""

# Check for any pod issues
echo "Checking for pod issues..."
UNHEALTHY_PODS=$(kubectl get pods -n moniker --field-selector=status.phase!=Running -o json | jq -r '.items[].metadata.name' || echo "")
if [ -n "$UNHEALTHY_PODS" ]; then
    echo "⚠️  Found unhealthy pods:"
    echo "$UNHEALTHY_PODS"
    echo ""
    echo "Recent events:"
    kubectl get events -n moniker --sort-by='.lastTimestamp' | tail -20
else
    echo "✅ All pods are healthy"
fi
echo ""

# Check database connectivity (from admin pod)
echo "Testing database connectivity..."
ADMIN_POD=$(kubectl get pods -n moniker -l app=moniker-admin -o jsonpath='{.items[0].metadata.name}')
if [ -n "$ADMIN_POD" ]; then
    echo "Testing from pod: $ADMIN_POD"
    DB_TEST=$(kubectl exec -n moniker "$ADMIN_POD" -- python3 -c "
import asyncio
import asyncpg
import os

async def test():
    try:
        conn = await asyncpg.connect(
            host=os.environ['TELEMETRY_DB_HOST'],
            port=int(os.environ['TELEMETRY_DB_PORT']),
            database=os.environ['TELEMETRY_DB_NAME'],
            user=os.environ['TELEMETRY_DB_USER'],
            password=os.environ['TELEMETRY_DB_PASSWORD']
        )
        result = await conn.fetchval('SELECT COUNT(*) FROM access_log')
        await conn.close()
        print(f'✅ Database connected. Access log has {result} events.')
    except Exception as e:
        print(f'❌ Database connection failed: {e}')

asyncio.run(test())
" 2>&1 || echo "❌ Database test failed")
    echo "$DB_TEST"
else
    echo "⚠️  Could not find admin pod for database test"
fi
echo ""

# Summary
echo "===================================="
echo "Health Check Summary"
echo "===================================="
echo "Java Resolver: http://${RESOLVER_LB}"
echo "Python Admin: http://${ADMIN_LB}"
echo "Dashboard: http://${ADMIN_LB}/dashboard"
echo ""
echo "To view logs:"
echo "  kubectl logs -f -n moniker -l app=moniker-resolver"
echo "  kubectl logs -f -n moniker -l app=moniker-admin"
echo ""
echo "To test telemetry:"
echo "  curl http://${RESOLVER_LB}/resolve/test/path@latest"
echo "  # Wait a few seconds, then check dashboard"
echo "  open http://${ADMIN_LB}/dashboard"
