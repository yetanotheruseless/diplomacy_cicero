#!/bin/bash
# Script to properly set up and test Diplomacy Cicero in Docker

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

print_header "DIPLOMACY CICERO DOCKER SETUP AND TEST"
print_warning "This script will build and test the Diplomacy Cicero Docker container"

# Step 1: Ensure Docker is running
print_header "STEP 1: CHECKING DOCKER"
if ! docker info >/dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker and try again."
    exit 1
else
    print_success "Docker is running"
fi

# Step 2: Build the Docker image if it doesn't exist
print_header "STEP 2: BUILDING DOCKER IMAGE"
if docker images | grep -q "diplomacy_cicero"; then
    print_warning "Docker image already exists. Rebuilding to ensure consistency..."
else
    print_warning "Building Docker image for the first time..."
fi

if docker-compose build; then
    print_success "Docker image built successfully"
else
    print_error "Failed to build Docker image. Please check the error messages above."
    exit 1
fi

# Step 3: Verify the container can start
print_header "STEP 3: TESTING CONTAINER STARTUP"
if docker-compose run --rm diplomacy echo "Container started successfully"; then
    print_success "Container started successfully"
else
    print_error "Failed to start container"
    exit 1
fi

# Step 4: Verify the protobuf compilation
print_header "STEP 4: COMPILING PROTOBUF FILES"
if docker-compose run --rm diplomacy bash -c "cd /app && make protos_basic"; then
    print_success "Protobuf files compiled successfully"
else
    print_error "Failed to compile protobuf files"
    exit 1
fi

# Step 5: Verify the dipcc module is built
print_header "STEP 5: VERIFYING DIPCC MODULE"
if docker-compose run --rm diplomacy bash -c "cd /app && python test_pydipcc.py"; then
    print_success "dipcc module is working correctly"
else
    print_warning "dipcc module test failed, attempting to rebuild..."
    if docker-compose run --rm diplomacy bash -c "cd /app && PYDIPCC_OUT_DIR=/app/fairdiplomacy SKIP_TESTS=1 bash ./dipcc/compile.sh"; then
        print_success "dipcc module rebuilt successfully"
        # Test again
        if docker-compose run --rm diplomacy bash -c "cd /app && python test_pydipcc.py"; then
            print_success "dipcc module is now working correctly"
        else
            print_error "dipcc module still failing after rebuild"
            exit 1
        fi
    else
        print_error "Failed to rebuild dipcc module"
        exit 1
    fi
fi

# Step 6: Test importing heyhi (after protobuf compilation)
print_header "STEP 6: TESTING HEYHI IMPORT"
if docker-compose run --rm diplomacy bash -c "cd /app && python -c \"import heyhi; print('Successfully imported heyhi')\""; then
    print_success "heyhi module imported successfully"
else
    print_warning "heyhi import failed, attempting to fix protobuf files..."
    if docker-compose run --rm diplomacy bash -c "cd /app && python scripts/fix_protos.py"; then
        print_success "Fixed protobuf files"
        # Try import again
        if docker-compose run --rm diplomacy bash -c "cd /app && python -c \"import heyhi; print('Successfully imported heyhi')\""; then
            print_success "heyhi module now imports successfully"
        else
            print_error "heyhi module still fails to import"
            
            # Debugging: Let's see what's wrong with the protobuf files
            docker-compose run --rm diplomacy bash -c "cd /app && find conf -name '*_pb2.py' -exec ls -la {} \;"
            docker-compose run --rm diplomacy bash -c "cd /app && cat conf/conf_pb2.py | head -20"
            
            exit 1
        fi
    else
        print_error "Failed to fix protobuf files"
        exit 1
    fi
fi

# Step 7: Test run.py command line
print_header "STEP 7: TESTING RUN.PY"
if docker-compose run --rm diplomacy bash -c "cd /app && python run.py --help | grep 'usage:'"; then
    print_success "run.py command line help works correctly"
else
    print_error "run.py command line help failed"
    exit 1
fi

# Step 8: Final success message
print_header "SETUP COMPLETE"
print_success "Diplomacy Cicero is correctly set up in Docker!"
print_warning "To run a game, use:"
echo "docker-compose run --rm diplomacy bash -c \"cd /app && python run.py --adhoc --cfg conf/c01_ag_cmp/cmp.prototxt Iagent_one=agents/cicero.prototxt Iagent_six=agents/ablations/cicero_imitation_only.prototxt power_one=TURKEY\""
echo ""