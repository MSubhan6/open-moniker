#!/bin/bash
set -euo pipefail

# Comprehensive deployment testing suite
# Tests all three deployment targets locally

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

FAILED_TESTS=()
PASSED_TESTS=()

log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
    PASSED_TESTS+=("$1")
}

log_error() {
    echo -e "${RED}✗${NC} $1"
    FAILED_TESTS+=("$1")
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

section_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# Change to repo root
cd "$(dirname "$0")/.."

section_header "0. Pre-flight Checks"

# Check required tools
log_info "Checking required tools..."

command -v python3 >/dev/null 2>&1 && log_success "python3 found" || log_error "python3 not found"
command -v java >/dev/null 2>&1 && log_success "java found" || log_error "java not found"
command -v mvn >/dev/null 2>&1 && log_success "maven found" || log_warning "maven not found (optional)"
command -v docker >/dev/null 2>&1 && log_success "docker found" || log_warning "docker not found (needed for Render/AWS)"
command -v terraform >/dev/null 2>&1 && log_success "terraform found" || log_warning "terraform not found (needed for AWS)"
command -v kubectl >/dev/null 2>&1 && log_success "kubectl found" || log_warning "kubectl not found (needed for AWS)"
command -v kustomize >/dev/null 2>&1 && log_success "kustomize found" || log_warning "kustomize not found (needed for AWS)"

# Check Java version
if command -v java >/dev/null 2>&1; then
    JAVA_VERSION=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | cut -d'.' -f1)
    if [ "$JAVA_VERSION" -ge 17 ]; then
        log_success "Java version $JAVA_VERSION (>= 17 required)"
    else
        log_error "Java version $JAVA_VERSION (>= 17 required)"
    fi
fi

section_header "1. Testing Java Resolver Build"

log_info "Building Java resolver..."
cd resolver-java

# Try mvnw first, fall back to mvn
if [ -f ./mvnw ]; then
    BUILD_CMD="./mvnw"
else
    BUILD_CMD="mvn"
fi

if $BUILD_CMD clean package -DskipTests -q; then
    log_success "Java resolver builds successfully"

    # Check JAR exists
    if [ -f target/resolver-*.jar ]; then
        JAR_SIZE=$(du -h target/resolver-*.jar | cut -f1)
        log_success "JAR created: $JAR_SIZE"
    else
        log_error "JAR file not found in target/"
    fi
else
    log_error "Java resolver build failed"
fi

cd ..

section_header "2. Testing Python Dependencies"

log_info "Checking Python dependencies..."

# Check if we can import required modules
python3 -c "import fastapi" 2>/dev/null && log_success "fastapi available" || log_error "fastapi not installed"
python3 -c "import uvicorn" 2>/dev/null && log_success "uvicorn available" || log_error "uvicorn not installed"
python3 -c "import aiosqlite" 2>/dev/null && log_success "aiosqlite available" || log_error "aiosqlite not installed"
python3 -c "import asyncpg" 2>/dev/null && log_success "asyncpg available" || log_error "asyncpg not installed"
python3 -c "import yaml" 2>/dev/null && log_success "pyyaml available" || log_error "pyyaml not installed"

section_header "3. Testing Local Deployment Structure"

log_info "Validating local deployment files..."

# Check bootstrap script
if [ -f deployments/local/bootstrap.py ]; then
    log_success "bootstrap.py exists"

    # Check if it's executable or can be run with python
    if python3 deployments/local/bootstrap.py --help > /dev/null 2>&1; then
        log_success "bootstrap.py can be executed"
    else
        log_warning "bootstrap.py --help failed (might be OK)"
    fi
else
    log_error "bootstrap.py not found"
fi

# Check requirements
if [ -f deployments/local/requirements.txt ]; then
    log_success "requirements.txt exists"
else
    log_error "requirements.txt not found"
fi

section_header "4. Testing Render.com Deployment"

log_info "Validating Render deployment files..."

# Check render.yaml
if [ -f deployments/render/render.yaml ]; then
    log_success "render.yaml exists"

    # Validate YAML syntax
    if python3 -c "import yaml; yaml.safe_load(open('deployments/render/render.yaml'))" 2>/dev/null; then
        log_success "render.yaml is valid YAML"
    else
        log_error "render.yaml has syntax errors"
    fi
else
    log_error "render.yaml not found"
fi

# Check Dockerfiles
if [ -f deployments/render/Dockerfile.java ]; then
    log_success "Dockerfile.java exists"
else
    log_error "Dockerfile.java not found"
fi

if [ -f deployments/render/Dockerfile.python ]; then
    log_success "Dockerfile.python exists"
else
    log_error "Dockerfile.python not found"
fi

# Test Docker builds (if Docker available)
if command -v docker >/dev/null 2>&1; then
    log_info "Testing Docker builds (this may take a while)..."

    # Test Java Dockerfile
    log_info "Building Java resolver Docker image..."
    if docker build -f deployments/render/Dockerfile.java -t test-java-resolver . > /tmp/docker-java.log 2>&1; then
        IMAGE_SIZE=$(docker images test-java-resolver --format "{{.Size}}" | head -1)
        log_success "Java Docker image builds successfully ($IMAGE_SIZE)"
    else
        log_error "Java Docker build failed (see /tmp/docker-java.log)"
        tail -20 /tmp/docker-java.log
    fi

    # Test Python Dockerfile
    log_info "Building Python admin Docker image..."
    if docker build -f deployments/render/Dockerfile.python -t test-python-admin . > /tmp/docker-python.log 2>&1; then
        IMAGE_SIZE=$(docker images test-python-admin --format "{{.Size}}" | head -1)
        log_success "Python Docker image builds successfully ($IMAGE_SIZE)"
    else
        log_error "Python Docker build failed (see /tmp/docker-python.log)"
        tail -20 /tmp/docker-python.log
    fi
else
    log_warning "Docker not available, skipping build tests"
fi

section_header "5. Testing AWS Terraform Configuration"

log_info "Validating Terraform configuration..."

cd deployments/aws/terraform

# Check Terraform files exist
if [ -f main.tf ]; then
    log_success "main.tf exists"
else
    log_error "main.tf not found"
fi

if [ -f variables.tf ]; then
    log_success "variables.tf exists"
else
    log_error "variables.tf not found"
fi

if [ -f outputs.tf ]; then
    log_success "outputs.tf exists"
else
    log_error "outputs.tf not found"
fi

# Check modules
for module in vpc eks aurora dns; do
    if [ -d "modules/$module" ]; then
        log_success "Module $module exists"

        # Check module files
        if [ -f "modules/$module/main.tf" ]; then
            log_success "  - modules/$module/main.tf exists"
        else
            log_error "  - modules/$module/main.tf missing"
        fi

        if [ -f "modules/$module/variables.tf" ]; then
            log_success "  - modules/$module/variables.tf exists"
        else
            log_error "  - modules/$module/variables.tf missing"
        fi

        if [ -f "modules/$module/outputs.tf" ]; then
            log_success "  - modules/$module/outputs.tf exists"
        else
            log_error "  - modules/$module/outputs.tf missing"
        fi
    else
        log_error "Module $module not found"
    fi
done

# Check environment configs
for env in dev staging prod; do
    if [ -f "environments/${env}.tfvars" ]; then
        log_success "${env}.tfvars exists"
    else
        log_error "${env}.tfvars not found"
    fi
done

# Validate Terraform syntax (if terraform available)
if command -v terraform >/dev/null 2>&1; then
    log_info "Running terraform fmt check..."
    if terraform fmt -check -recursive . > /dev/null 2>&1; then
        log_success "Terraform formatting is correct"
    else
        log_warning "Terraform formatting could be improved (run 'terraform fmt -recursive')"
    fi

    log_info "Running terraform validate..."
    terraform init -backend=false > /tmp/terraform-init.log 2>&1
    if terraform validate > /tmp/terraform-validate.log 2>&1; then
        log_success "Terraform configuration is valid"
    else
        log_error "Terraform validation failed (see /tmp/terraform-validate.log)"
        cat /tmp/terraform-validate.log
    fi
else
    log_warning "Terraform not available, skipping validation"
fi

cd ../../..

section_header "6. Testing Kubernetes Manifests"

log_info "Validating Kubernetes manifests..."

cd deployments/aws/kubernetes

# Check base files
if [ -d base ]; then
    log_success "base directory exists"

    for file in namespace.yaml java-resolver.yaml python-admin.yaml configmap.yaml secrets.yaml kustomization.yaml; do
        if [ -f "base/$file" ]; then
            log_success "  - base/$file exists"
        else
            log_error "  - base/$file missing"
        fi
    done
else
    log_error "base directory not found"
fi

# Check overlays
for region in us-east-1 us-west-2; do
    if [ -d "overlays/$region" ]; then
        log_success "overlays/$region exists"

        if [ -f "overlays/$region/kustomization.yaml" ]; then
            log_success "  - overlays/$region/kustomization.yaml exists"
        else
            log_error "  - overlays/$region/kustomization.yaml missing"
        fi
    else
        log_error "overlays/$region not found"
    fi
done

# Validate with kubectl (if available)
if command -v kubectl >/dev/null 2>&1; then
    log_info "Running kubectl dry-run on base manifests..."

    if kubectl apply --dry-run=client -k base > /tmp/kubectl-base.log 2>&1; then
        log_success "Base Kubernetes manifests are valid"
    else
        log_error "Base Kubernetes manifests validation failed (see /tmp/kubectl-base.log)"
        cat /tmp/kubectl-base.log
    fi
else
    log_warning "kubectl not available, skipping manifest validation"
fi

# Validate with kustomize (if available)
if command -v kustomize >/dev/null 2>&1; then
    log_info "Running kustomize build..."

    if kustomize build base > /tmp/kustomize-base.yaml 2>/dev/null; then
        MANIFEST_SIZE=$(wc -l < /tmp/kustomize-base.yaml)
        log_success "Kustomize build successful ($MANIFEST_SIZE lines)"
    else
        log_error "Kustomize build failed"
    fi

    # Test overlays
    for region in us-east-1 us-west-2; do
        if kustomize build overlays/$region > /tmp/kustomize-$region.yaml 2>/dev/null; then
            MANIFEST_SIZE=$(wc -l < /tmp/kustomize-$region.yaml)
            log_success "Kustomize build successful for $region ($MANIFEST_SIZE lines)"
        else
            log_error "Kustomize build failed for $region"
        fi
    done
else
    log_warning "kustomize not available, skipping build tests"
fi

cd ../../..

section_header "7. Testing Deployment Scripts"

log_info "Validating deployment scripts..."

# Check scripts exist and are executable
for script in deploy.sh migrate-db.sh health-check.sh; do
    if [ -f "deployments/aws/scripts/$script" ]; then
        log_success "deployments/aws/scripts/$script exists"

        if [ -x "deployments/aws/scripts/$script" ]; then
            log_success "  - $script is executable"
        else
            log_warning "  - $script is not executable (should chmod +x)"
        fi

        # Check for bash syntax errors
        if bash -n "deployments/aws/scripts/$script" 2>/dev/null; then
            log_success "  - $script has valid bash syntax"
        else
            log_error "  - $script has bash syntax errors"
        fi
    else
        log_error "deployments/aws/scripts/$script not found"
    fi
done

section_header "8. Testing Documentation"

log_info "Checking documentation completeness..."

# Check READMEs
if [ -f deployments/README.md ]; then
    log_success "deployments/README.md exists"
else
    log_error "deployments/README.md not found"
fi

if [ -f deployments/local/README.md ]; then
    log_success "deployments/local/README.md exists"
else
    log_error "deployments/local/README.md not found"
fi

if [ -f deployments/render/README.md ]; then
    log_success "deployments/render/README.md exists"
else
    log_error "deployments/render/README.md not found"
fi

if [ -f deployments/aws/README.md ]; then
    log_success "deployments/aws/README.md exists"

    # Check README size (should be comprehensive)
    README_LINES=$(wc -l < deployments/aws/README.md)
    if [ "$README_LINES" -gt 300 ]; then
        log_success "  - AWS README is comprehensive ($README_LINES lines)"
    else
        log_warning "  - AWS README might be incomplete ($README_LINES lines)"
    fi
else
    log_error "deployments/aws/README.md not found"
fi

if [ -f deployments/aws/DEPLOYMENT_CHECKLIST.md ]; then
    log_success "deployments/aws/DEPLOYMENT_CHECKLIST.md exists"
else
    log_error "deployments/aws/DEPLOYMENT_CHECKLIST.md not found"
fi

section_header "9. Testing Java Telemetry"

log_info "Checking Java telemetry implementation..."

# Check telemetry package exists
if [ -d resolver-java/src/main/java/com/ganizanisitara/moniker/resolver/telemetry ]; then
    log_success "Java telemetry package exists"

    # Check key classes
    for class in UsageEvent.java Emitter.java Batcher.java Sink.java EventOutcome.java Operation.java CallerIdentity.java; do
        if [ -f "resolver-java/src/main/java/com/ganizanisitara/moniker/resolver/telemetry/$class" ]; then
            log_success "  - $class exists"
        else
            log_error "  - $class missing"
        fi
    done

    # Check sinks
    for sink in ConsoleSink.java SQLiteSink.java PostgresSink.java; do
        if [ -f "resolver-java/src/main/java/com/ganizanisitara/moniker/resolver/telemetry/sinks/$sink" ]; then
            log_success "  - sinks/$sink exists"
        else
            log_error "  - sinks/$sink missing"
        fi
    done

    # Check factory
    if [ -f "resolver-java/src/main/java/com/ganizanisitara/moniker/resolver/telemetry/factory/TelemetryFactory.java" ]; then
        log_success "  - TelemetryFactory exists"
    else
        log_error "  - TelemetryFactory missing"
    fi
else
    log_error "Java telemetry package not found"
fi

section_header "10. Testing Python Telemetry"

log_info "Checking Python telemetry implementation..."

# Check dashboard module
if [ -d src/moniker_svc/dashboard ]; then
    log_success "Python dashboard module exists"

    if [ -f src/moniker_svc/dashboard/routes.py ]; then
        log_success "  - routes.py exists"

        # Check for WebSocket endpoint
        if grep -q "@router.websocket" src/moniker_svc/dashboard/routes.py; then
            log_success "  - WebSocket endpoint found in routes.py"
        else
            log_error "  - WebSocket endpoint not found in routes.py"
        fi
    else
        log_error "  - routes.py missing"
    fi

    if [ -f src/moniker_svc/dashboard/static/index.html ]; then
        log_success "  - static/index.html exists"

        # Check for Chart.js and WebSocket
        if grep -q "Chart.js" src/moniker_svc/dashboard/static/index.html; then
            log_success "  - Chart.js integration found"
        else
            log_warning "  - Chart.js integration not found"
        fi

        if grep -q "WebSocket" src/moniker_svc/dashboard/static/index.html; then
            log_success "  - WebSocket client found"
        else
            log_error "  - WebSocket client not found"
        fi
    else
        log_error "  - static/index.html missing"
    fi
else
    log_error "Python dashboard module not found"
fi

# Check telemetry db module
if [ -f src/moniker_svc/telemetry/db.py ]; then
    log_success "Python telemetry db.py exists"

    # Check for async functions
    if grep -q "async def" src/moniker_svc/telemetry/db.py; then
        log_success "  - Async functions found"
    else
        log_error "  - No async functions found"
    fi
else
    log_error "Python telemetry db.py not found"
fi

section_header "Test Summary"

echo ""
echo "Passed tests: ${#PASSED_TESTS[@]}"
echo "Failed tests: ${#FAILED_TESTS[@]}"
echo ""

if [ ${#FAILED_TESTS[@]} -eq 0 ]; then
    log_success "All tests passed! 🎉"
    echo ""
    echo "Next steps:"
    echo "  1. Test local deployment: cd deployments/local && python3 bootstrap.py dev"
    echo "  2. Build Docker images: cd deployments/render && docker build -f Dockerfile.java -t moniker-java ../.. "
    echo "  3. Deploy to AWS: cd deployments/aws/terraform && terraform init && terraform plan"
    exit 0
else
    log_error "Some tests failed:"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
    echo ""
    echo "Please fix the failures before deploying."
    exit 1
fi
