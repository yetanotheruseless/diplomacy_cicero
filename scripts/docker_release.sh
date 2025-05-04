#!/bin/bash
# Script to build and tag Docker images for release

# Default settings
VERSION="1.0.0"
ARCH=$(uname -m)
BUILD_TYPE="full"
REGISTRY=""
PUSH=false
JOBS=2
MEMORY=""

# Parse command line arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --arch)
      ARCH="$2"
      shift 2
      ;;
    --build-type)
      BUILD_TYPE="$2"
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
    --jobs)
      JOBS="$2"
      shift 2
      ;;
    --memory)
      MEMORY="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --version VERSION    Specify version tag (default: 1.0.0)"
      echo "  --arch ARCH          CPU architecture (x86_64 or arm64, default: detected)"
      echo "  --build-type TYPE    Build type (full or minimal, default: full)"
      echo "  --registry REG       Container registry prefix (e.g., ghcr.io/yourorg)"
      echo "  --push               Push images to registry after building"
      echo "  --jobs NUMBER        Number of parallel build jobs (default: 2)"
      echo "  --memory LIMIT       Memory limit for build (e.g., 4g for 4GB)"
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

# Set image name and tags
IMAGE_NAME="diplomacy_cicero"
VERSION_ARCH_TAG="${VERSION}-${ARCH}-${BUILD_TYPE}"
FULL_TAG="${IMAGE_NAME}:${VERSION_ARCH_TAG}"

# If registry is specified, also create a registry tag
if [ -n "$REGISTRY" ]; then
  REGISTRY_TAG="${REGISTRY}/${IMAGE_NAME}:${VERSION_ARCH_TAG}"
fi

echo "========================================================"
echo "  Docker Release Build for Diplomacy Cicero"
echo "========================================================"
echo "Version:       $VERSION"
echo "Architecture:  $ARCH"
echo "Build Type:    $BUILD_TYPE"
echo "Build Jobs:    $JOBS"
if [ -n "$MEMORY" ]; then
  echo "Memory Limit:  $MEMORY"
fi
echo "Local Tag:     $FULL_TAG"
if [ -n "$REGISTRY" ]; then
  echo "Registry Tag:  $REGISTRY_TAG"
fi
echo "Push to Registry: $PUSH"
echo "========================================================"
echo

# Confirm build
read -p "Do you want to proceed with this build? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Build cancelled"
  exit 1
fi

# Build the image
echo "Building Docker image..."
BUILD_ARGS="--build-arg DIPCC_BUILD_JOBS=$JOBS"

if [ -n "$MEMORY" ]; then
  BUILD_ARGS="$BUILD_ARGS --memory=$MEMORY"
fi

if [ "$BUILD_TYPE" = "minimal" ]; then
  BUILD_ARGS="$BUILD_ARGS --build-arg MINIMAL=true"
fi

# Build the image with appropriate tags
docker build -t "$FULL_TAG" -f Dockerfile.unified $BUILD_ARGS .

# Check build status
if [ $? -ne 0 ]; then
  echo "Error: Docker build failed"
  exit 1
else
  echo "Successfully built: $FULL_TAG"
fi

# Tag with registry if specified
if [ -n "$REGISTRY" ]; then
  echo "Tagging image for registry: $REGISTRY_TAG"
  docker tag "$FULL_TAG" "$REGISTRY_TAG"
  
  # Push to registry if requested
  if [ "$PUSH" = true ]; then
    echo "Pushing image to registry..."
    docker push "$REGISTRY_TAG"
    
    if [ $? -ne 0 ]; then
      echo "Error: Failed to push image to registry"
      exit 1
    else
      echo "Successfully pushed: $REGISTRY_TAG"
    fi
  fi
fi

# Run tests on the image
echo "Running tests on the built image..."
docker run --rm "$FULL_TAG" python /app/test_pydipcc.py

if [ $? -ne 0 ]; then
  echo "Warning: Tests failed on the built image"
else
  echo "Tests passed successfully"
fi

echo
echo "========================================================"
echo "  Release Build Complete"
echo "========================================================"
echo "Image:         $FULL_TAG"
if [ -n "$REGISTRY" ] && [ "$PUSH" = true ]; then
  echo "Registry:      $REGISTRY_TAG (pushed)"
elif [ -n "$REGISTRY" ]; then
  echo "Registry:      $REGISTRY_TAG (not pushed)"
fi
echo
echo "To use this image:"
echo "docker run -it --rm $FULL_TAG bash"
echo
echo "To create a multi-architecture manifest:"
echo "docker manifest create $IMAGE_NAME:$VERSION \\"
echo "  $IMAGE_NAME:$VERSION-x86_64-$BUILD_TYPE \\"
echo "  $IMAGE_NAME:$VERSION-arm64-$BUILD_TYPE"
echo
if [ -n "$REGISTRY" ]; then
  echo "For registry manifest:"
  echo "docker manifest create $REGISTRY/$IMAGE_NAME:$VERSION \\"
  echo "  $REGISTRY/$IMAGE_NAME:$VERSION-x86_64-$BUILD_TYPE \\"
  echo "  $REGISTRY/$IMAGE_NAME:$VERSION-arm64-$BUILD_TYPE"
fi
echo "========================================================"