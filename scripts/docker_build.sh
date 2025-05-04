#!/bin/bash
# Script to build the Docker image for Diplomacy Cicero

# Default settings
DOCKERFILE="Dockerfile.unified"
BUILD_JOBS=2
MEMORY_LIMIT=""

# Parse command line arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    --file)
      DOCKERFILE="$2"
      shift 2
      ;;
    --jobs)
      BUILD_JOBS="$2"
      shift 2
      ;;
    --memory)
      MEMORY_LIMIT="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --file DOCKERFILE  Specify which Dockerfile to use (default: Dockerfile.unified)"
      echo "  --jobs NUMBER      Number of parallel build jobs (default: 2)"
      echo "  --memory LIMIT     Memory limit for build (e.g., 4g for 4GB)"
      echo "  --help             Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run '$0 --help' for usage information"
      exit 1
      ;;
  esac
done

echo "Building Docker image for Diplomacy Cicero..."
echo "Using Dockerfile: $DOCKERFILE"
echo "Build parallelism: $BUILD_JOBS jobs"

# Set up build arguments
BUILD_ARGS="--build-arg DIPCC_BUILD_JOBS=$BUILD_JOBS"

# Add memory limit if specified
if [ -n "$MEMORY_LIMIT" ]; then
  echo "Memory limit: $MEMORY_LIMIT"
  MEMORY_OPTION="--memory=$MEMORY_LIMIT"
else
  MEMORY_OPTION=""
fi

# Update docker-compose.yml with the selected Dockerfile
sed -i.bak "s|dockerfile: Dockerfile.*|dockerfile: $DOCKERFILE|g" docker-compose.yml
sed -i.bak "s|DIPCC_BUILD_JOBS: .*|DIPCC_BUILD_JOBS: $BUILD_JOBS|g" docker-compose.yml

# Build the image
docker-compose build $MEMORY_OPTION

echo "Docker image built successfully."
echo "To start a container, run: ./scripts/docker_run.sh"