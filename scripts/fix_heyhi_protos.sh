#!/bin/bash
# Script to fix protobuf files for heyhi compatibility

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

# Make sure we're in the project root
cd "$(dirname "$0")/.." || exit 1

print_header "FIXING PROTOBUF FILES FOR HEYHI"
print_warning "This script will compile and patch protobuf files"

# Clean up any orphaned containers
print_header "CLEANING UP DOCKER ENVIRONMENT"
docker-compose down --remove-orphans

# Step 1: Ensure Docker is running
print_header "STEP 1: CHECKING DOCKER"
if ! docker info >/dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker and try again."
    exit 1
else
    print_success "Docker is running"
fi

# Step 2: Compile protobuf files
print_header "STEP 2: COMPILING PROTOBUF FILES"
docker-compose run --rm diplomacy bash -c "cd /app && make protos_basic"
if [ $? -eq 0 ]; then
    print_success "Protobuf files compiled successfully"
else
    print_error "Failed to compile protobuf files"
    exit 1
fi

# Step 3: Run the protobuf patch script
print_header "STEP 3: PATCHING PROTOBUF FILES"
docker-compose run --rm diplomacy bash -c "cd /app && python heyhi/bin/patch_protos.py conf/*_pb2.py"
if [ $? -eq 0 ]; then
    print_success "Protobuf files patched successfully"
else
    print_error "Failed to patch protobuf files"
    exit 1
fi

# Step 4: Test importing heyhi
print_header "STEP 4: TESTING HEYHI IMPORT"
docker-compose run --rm diplomacy bash -c "cd /app && python -c \"import heyhi; print('Successfully imported heyhi'); print('PROJ_ROOT:', heyhi.PROJ_ROOT)\""
if [ $? -eq 0 ]; then
    print_success "heyhi module imported successfully"
else
    print_error "heyhi import failed"
    exit 1
fi

# Step 5: Check if run.py works
print_header "STEP 5: TESTING RUN.PY"
docker-compose run --rm diplomacy bash -c "cd /app && python run.py --help | grep 'usage:'"
if [ $? -eq 0 ]; then
    print_success "run.py command line help works correctly"
else
    print_error "run.py command line help failed"
    exit 1
fi

# Final success message
print_header "PATCHING COMPLETE"
print_success "Protobuf files have been fixed and heyhi module is working correctly!"
print_warning "To run a game, use:"
echo "docker-compose run --rm diplomacy bash -c \"cd /app && python run.py --adhoc --cfg conf/c01_ag_cmp/cmp.prototxt Iagent_one=agents/cicero.prototxt Iagent_six=agents/ablations/cicero_imitation_only.prototxt power_one=TURKEY\""
echo ""