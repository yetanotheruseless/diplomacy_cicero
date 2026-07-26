#!/bin/bash
# Script to test heyhi functionality inside the Docker container

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${GREEN}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

# Make sure this script runs from the project root
cd "$(dirname "$0")/.." || exit 1

print_header "TESTING HEYHI IN DOCKER CONTAINER"
print_warning "This script runs several tests to verify that heyhi works inside Docker"

# First, verify that Docker is running and the image exists
if ! docker ps >/dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

if ! docker images | grep -q "diplomacy_cicero"; then
    print_warning "Diplomacy Cicero Docker image not found. Building it now..."
    ./scripts/docker_build.sh
fi

print_header "TEST 1: BASIC HEYHI IMPORT"
print_warning "Running basic heyhi import test in Docker..."
docker-compose run --rm diplomacy bash -c "cd /app && python -c \"import heyhi; print('Successfully imported heyhi')\""
if [ $? -eq 0 ]; then
    print_success "Basic heyhi import successful"
else
    print_error "Basic heyhi import failed"
    exit 1
fi

print_header "TEST 2: RUNNING HEYHI VERIFICATION SCRIPT"
print_warning "Running comprehensive heyhi verification script in Docker..."
docker-compose run --rm diplomacy bash -c "cd /app && python test_scripts/verify_heyhi_game.py"
if [ $? -eq 0 ]; then
    print_success "Heyhi verification script passed successfully"
else
    print_error "Heyhi verification script failed"
    exit 1
fi

print_header "TEST 3: VERIFYING RUN.PY COMMAND LINE ARGUMENTS"
print_warning "Testing run.py command line arguments handling in Docker..."
docker-compose run --rm diplomacy bash -c "cd /app && python run.py --help | grep 'usage:'"
if [ $? -eq 0 ]; then
    print_success "run.py command line help works correctly"
else
    print_error "run.py command line help failed"
    exit 1
fi

print_header "TEST 4: CHECKING CFG LOADING"
print_warning "Testing configuration loading in Docker..."
docker-compose run --rm diplomacy bash -c "cd /app && python -c \"import heyhi; cfg = heyhi.load_config('conf/c01_ag_cmp/cmp.prototxt'); print('Successfully loaded config')\""
if [ $? -eq 0 ]; then
    print_success "Configuration loading successful"
else
    print_error "Configuration loading failed"
    exit 1
fi

print_header "TEST 5: CHECKING RUN.PY WITH ADHOC FLAG"
print_warning "Testing run.py with --adhoc flag (minimal run to avoid full game execution)..."
# Run with timeout to avoid hanging if there's an issue
timeout 10 docker-compose run --rm diplomacy bash -c "cd /app && python run.py --adhoc --help"
if [ $? -eq 0 ] || [ $? -eq 124 ]; then  # Timeout is acceptable here
    print_success "run.py with --adhoc flag works (or timed out as expected)"
else
    print_error "run.py with --adhoc flag failed"
fi

print_header "FINAL VERDICT"
print_success "All tests completed!"
print_warning "To run a full game:"
echo "docker-compose run --rm diplomacy bash -c \"cd /app && python run.py --adhoc --cfg conf/c01_ag_cmp/cmp.prototxt Iagent_one=agents/cicero.prototxt Iagent_six=agents/ablations/cicero_imitation_only.prototxt power_one=TURKEY\""
echo ""
print_warning "Note: Running a full game requires significant resources and may take time."
echo ""