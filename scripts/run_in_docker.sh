#!/bin/bash
# Script to safely run commands inside the Docker container

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Check if the Docker image exists
if ! docker images | grep -q "diplomacy_cicero"; then
    print_warning "Diplomacy Cicero Docker image not found. Building it now..."
    
    # Build the Docker image
    if ! ./scripts/docker_build.sh; then
        print_error "Failed to build Docker image. Please check the error messages above."
        exit 1
    fi
    
    print_success "Docker image built successfully."
fi

# Display a warning message
print_warning "RUNNING INSIDE DOCKER: Commands will execute inside the Docker container, not on your host system."
print_warning "This ensures the correct environment for Diplomacy Cicero code."

# Run the command in the Docker container
print_success "Executing inside container: $*"
docker-compose run --rm diplomacy bash -c "cd /app && $*"

# Check the exit status
exit_status=$?
if [ $exit_status -ne 0 ]; then
    print_error "Command failed with exit code $exit_status"
    exit $exit_status
else
    print_success "Command completed successfully"
fi