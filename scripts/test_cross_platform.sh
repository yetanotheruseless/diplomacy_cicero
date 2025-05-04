#!/bin/bash
# Script to test Docker build cross-platform compatibility (x86_64 and ARM64)

# Default settings
VERSION="test"
PUSH=false
REGISTRY=""
PLATFORMS="linux/amd64,linux/arm64"
TEST_COMMAND="python /app/test_pydipcc.py"

# Parse command line arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --registry)
      REGISTRY="$2"
      shift 2
      ;;
    --push)
      PUSH=true
      shift
      ;;
    --platforms)
      PLATFORMS="$2"
      shift 2
      ;;
    --test)
      TEST_COMMAND="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --version VERSION    Version tag for the image (default: test)"
      echo "  --registry REG       Container registry prefix (e.g., ghcr.io/yourorg)"
      echo "  --push               Push the multi-platform image"
      echo "  --platforms PLATS    Comma-separated list of platforms (default: linux/amd64,linux/arm64)"
      echo "  --test COMMAND       Command to run for testing (default: python /app/test_pydipcc.py)"
      echo "  --help               Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run '$0 --help' for usage information"
      exit 1
      ;;
  esac
done

# Set image name
IMAGE_NAME="diplomacy_cicero"
if [ -n "$REGISTRY" ]; then
  FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
else
  FULL_IMAGE="${IMAGE_NAME}:${VERSION}"
fi

echo "========================================================"
echo "  Cross-Platform Compatibility Test"
echo "========================================================"
echo "Image:           $FULL_IMAGE"
echo "Platforms:       $PLATFORMS"
echo "Test Command:    $TEST_COMMAND"
echo "Push Image:      $PUSH"
echo "========================================================"

# Check if Docker buildx is available
if ! docker buildx version > /dev/null 2>&1; then
  echo "Error: Docker buildx is not available. Please install Docker buildx:"
  echo "https://docs.docker.com/buildx/working-with-buildx/"
  exit 1
fi

# Create or use a builder with multi-platform support
BUILDER_NAME="diplomacy-cross-platform"
if ! docker buildx inspect "$BUILDER_NAME" > /dev/null 2>&1; then
  echo "Creating new buildx builder: $BUILDER_NAME"
  docker buildx create --name "$BUILDER_NAME" --platform "$PLATFORMS" --use
else
  echo "Using existing buildx builder: $BUILDER_NAME"
  docker buildx use "$BUILDER_NAME"
fi

# Display builder info
echo "Builder information:"
docker buildx inspect

# Build the image for all platforms
echo "Building multi-platform image..."
LOAD_OR_PUSH=""
if [ "$PUSH" = true ]; then
  LOAD_OR_PUSH="--push"
else
  LOAD_OR_PUSH="--load"
fi

# Use unified Dockerfile
docker buildx build \
  --platform "$PLATFORMS" \
  -t "$FULL_IMAGE" \
  -f Dockerfile.unified \
  $LOAD_OR_PUSH \
  --build-arg DIPCC_BUILD_JOBS=2 \
  .

if [ $? -ne 0 ]; then
  echo "Error: Failed to build multi-platform image"
  exit 1
fi

echo "Successfully built multi-platform image: $FULL_IMAGE"

# Test on current platform
CURRENT_ARCH=$(uname -m)
echo "Testing image on current architecture: $CURRENT_ARCH"

if docker run --rm "$FULL_IMAGE" $TEST_COMMAND; then
  echo "Test passed on $CURRENT_ARCH"
else
  echo "Warning: Test failed on $CURRENT_ARCH"
fi

# If we have qemu, we can test on other platforms
if command -v qemu-aarch64 > /dev/null 2>&1; then
  echo "QEMU found, can test other architectures"
  
  # List all platforms
  for PLATFORM in $(echo "$PLATFORMS" | tr ',' ' '); do
    ARCH=$(echo "$PLATFORM" | cut -d '/' -f 2)
    if [ "$ARCH" != "$CURRENT_ARCH" ]; then
      echo "Testing on $ARCH using QEMU..."
      if docker run --rm --platform "$PLATFORM" "$FULL_IMAGE" $TEST_COMMAND; then
        echo "Test passed on $ARCH"
      else
        echo "Warning: Test failed on $ARCH"
      fi
    fi
  done
else
  echo "QEMU not found, cannot test on non-native architectures"
  echo "To install QEMU for cross-platform emulation:"
  echo "  - On Ubuntu: sudo apt-get install qemu binfmt-support qemu-user-static"
  echo "  - On macOS: brew install qemu"
  echo "Then run: docker run --privileged --rm tonistiigi/binfmt --install all"
fi

echo
echo "========================================================"
echo "  Cross-Platform Test Complete"
echo "========================================================"
echo "Image:           $FULL_IMAGE"
echo "Platforms:       $PLATFORMS"
echo
echo "To pull this image:"
echo "docker pull $FULL_IMAGE"
echo
echo "To run this image on a specific platform:"
echo "docker run --platform linux/amd64 --rm $FULL_IMAGE bash"
echo "docker run --platform linux/arm64 --rm $FULL_IMAGE bash"
echo "========================================================"