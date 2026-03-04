#!/bin/bash
# Stress test the Java resolver using Python harness
# This is the main high-concurrency stress test

set -e

PORT=${1:-8054}
WORKERS=${2:-64}
DURATION=${3:-60}

echo "================================================================"
echo "  Java Resolver Stress Test (Python Harness)"
echo "================================================================"
echo "Port: $PORT"
echo "Workers: $WORKERS"
echo "Duration: ${DURATION}s"
echo ""

# Check if resolver is running
if ! curl -s http://localhost:$PORT/health > /dev/null 2>&1; then
    echo "❌ Java resolver not running on port $PORT"
    echo "Start it with: make run"
    exit 1
fi

echo "✅ Java resolver is running"
echo ""

# Check if stress harness exists
if [ ! -f "../tests/stress/harness.py" ]; then
    echo "Error: Stress harness not found at ../tests/stress/harness.py"
    exit 1
fi

# Run stress test
cd ../tests/stress
python3 harness.py --port $PORT --workers $WORKERS --duration $DURATION

echo ""
echo "================================================================"
echo "  Stress Test Complete"
echo "================================================================"
