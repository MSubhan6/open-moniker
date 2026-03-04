#!/bin/bash
# Quick benchmark script for Java resolver
# For high-concurrency stress testing, use stress-test.sh instead

set -e

JAVA_PORT=8054

echo "================================================================"
echo "  Java Resolver Quick Benchmark"
echo "================================================================"
echo ""

# Check if server is running
if ! curl -s http://localhost:$JAVA_PORT/health > /dev/null 2>&1; then
    echo "❌ Java resolver not running on port $JAVA_PORT"
    echo "Start it with: make run"
    exit 1
fi

echo "✅ Java resolver is running"
echo ""

# Test 1: Health endpoint latency
echo "=== Test 1: Health Endpoint (Sequential, 100 requests) ==="
time (for i in {1..100}; do curl -s http://localhost:$JAVA_PORT/health > /dev/null; done) 2>&1 | grep real
echo ""

# Test 2: Concurrent health endpoint
echo "=== Test 2: Health Endpoint (Concurrent, 200 requests) ==="
time (for i in {1..200}; do curl -s http://localhost:$JAVA_PORT/health > /dev/null & done; wait) 2>&1 | grep real
echo ""

# Test 3: Resolve endpoint latency
echo "=== Test 3: Resolve Endpoint (Sequential, 50 requests) ==="
TEST_PATH="prices.equity/AAPL@latest"
time (for i in {1..50}; do curl -s "http://localhost:$JAVA_PORT/resolve/$TEST_PATH" > /dev/null; done) 2>&1 | grep real
echo ""

# Test 4: Sample response
echo "=== Test 4: Sample Response ==="
curl -s "http://localhost:$JAVA_PORT/resolve/$TEST_PATH" | head -c 500
echo ""
echo ""

# Test 5: Catalog stats
echo "=== Test 5: Catalog Statistics ==="
curl -s "http://localhost:$JAVA_PORT/catalog/stats" | head -c 300
echo ""
echo ""

echo "================================================================"
echo "  Quick Benchmark Complete"
echo "================================================================"
echo ""
echo "For high-concurrency stress testing, run: ./stress-test.sh"
