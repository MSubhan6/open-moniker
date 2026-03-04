.PHONY: build test package run clean benchmark stress-test

# Build the project
build:
	mvn clean compile

# Run tests
test:
	mvn test

# Package as JAR
package:
	mvn clean package -DskipTests

# Run the resolver
run: package
	java -XX:+UseZGC \
	     -Xms1g -Xmx2g \
	     -jar target/resolver-java-0.1.0.jar \
	     --server.port=8054

# Run with custom config
run-with-config: package
	CONFIG_FILE=$(CONFIG_FILE) \
	java -XX:+UseZGC \
	     -Xms1g -Xmx2g \
	     -jar target/resolver-java-0.1.0.jar \
	     --server.port=$(PORT)

# Clean build artifacts
clean:
	mvn clean
	rm -f nohup.out

# Run stress test
stress-test: package
	./stress-test.sh

# Quick benchmark with hey
benchmark: package
	@echo "Starting Java resolver..."
	@java -XX:+UseZGC -Xms1g -Xmx2g \
	     -jar target/resolver-java-0.1.0.jar \
	     --server.port=8054 > /tmp/resolver-java.log 2>&1 &
	@echo $$! > /tmp/resolver-java.pid
	@sleep 5
	@echo "\n=== Health Endpoint Benchmark ==="
	@hey -n 10000 -c 200 http://localhost:8054/health || true
	@echo "\n=== Resolve Endpoint Benchmark ==="
	@hey -n 5000 -c 100 http://localhost:8054/resolve/prices.equity/AAPL@latest || true
	@kill `cat /tmp/resolver-java.pid` || true
	@rm -f /tmp/resolver-java.pid

# Help
help:
	@echo "Available targets:"
	@echo "  build         - Compile the project"
	@echo "  test          - Run unit tests"
	@echo "  package       - Build JAR file"
	@echo "  run           - Run the resolver (port 8054)"
	@echo "  clean         - Clean build artifacts"
	@echo "  stress-test   - Run Python stress harness"
	@echo "  benchmark     - Quick benchmark with hey"
	@echo "  help          - Show this help message"
