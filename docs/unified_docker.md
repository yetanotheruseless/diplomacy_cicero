# Unified Docker Build Process for Diplomacy Cicero

This document explains the new unified Docker build system for the Diplomacy Cicero project, which combines the features of both the regular and phased builds.

## Key Improvements

The unified Docker build process offers several improvements:

1. **Phased Building with Verification**: Each build phase is verified with appropriate tests
2. **Cross-Platform Compatibility**: Dynamic module loading for different architectures (x86_64, ARM64)
3. **Configurable Resource Usage**: Adjustable parallel build jobs to optimize memory usage
4. **Comprehensive Testing**: Enhanced testing of the pydipcc module
5. **Build Status Reporting**: Clear status indicators for each build phase

## Build Phases

The Dockerfile.unified follows a structured approach with the following phases:

1. **System dependencies**: Install core system packages and compiler toolchain
2. **Protobuf installation**: Build protobuf from source with version 3.19.1
3. **Protocol buffer compilation**: Compile the .proto files to Python
4. **dipcc C++ build**: Build the core C++ game engine
5. **Testing**: Verify the pydipcc module functionality
6. **Project requirements**: Install remaining Python dependencies
7. **Environment verification**: Final checks of the build environment

## Using the Unified Docker Build

### Building the Image

To build using the unified Dockerfile:

```bash
# Build with default settings
docker build -t diplomacy_cicero:unified -f Dockerfile.unified .

# Build with custom settings
docker build -t diplomacy_cicero:unified -f Dockerfile.unified \
  --build-arg DIPCC_BUILD_JOBS=4 .
```

### Using with Docker Compose

The updated docker-compose.yml includes two services:

1. `diplomacy`: Main development environment with full codebase
2. `diplomacy_test`: Lightweight service for testing only

```bash
# Start the main service
docker-compose up -d diplomacy

# Run just the tests
docker-compose run --rm diplomacy_test

# Access the running container
docker-compose exec diplomacy bash
```

### Build Arguments

The Dockerfile supports the following build arguments:

| Argument | Default | Description |
|----------|---------|-------------|
| DIPCC_BUILD_JOBS | 2 | Number of parallel jobs for C++ compilation |

Example:
```bash
docker-compose build --build-arg DIPCC_BUILD_JOBS=4 diplomacy
```

## Multi-Architecture Support

The unified build process supports multiple CPU architectures:

- **x86_64** (Intel/AMD): Standard desktop/server architecture
- **ARM64** (Apple Silicon/AWS Graviton): Newer MacBooks and some cloud instances

The module loading code in `fairdiplomacy/__init__.py` dynamically detects the appropriate shared library for your platform.

## Troubleshooting

If you encounter build failures:

1. **Memory Issues**:
   - Reduce DIPCC_BUILD_JOBS to 1
   - Increase Docker memory allocation (in Docker Desktop settings)

2. **Module Loading Issues**:
   - Check if the .so file exists: `find /app -name "pydipcc*.so"`
   - Run the test script manually: `python /app/test_pydipcc.py`

3. **Protobuf Issues**:
   - Verify protobuf version: `protoc --version`
   - Check Python protobuf: `python -c "import google.protobuf; print(google.protobuf.__version__)"`

## Cross-Platform Development Workflow

For developers working across different platforms:

1. Build the Docker image on each target platform
2. Use Docker Compose to maintain consistent environments
3. Use the included test scripts to verify functionality
4. Mount your codebase using the volume mappings for live editing

## Benefits of the Unified Approach

This unified approach provides several advantages over the previous separate Dockerfiles:

1. **Simplified maintenance**: One Dockerfile to maintain instead of two
2. **Better visibility**: Clear phase markers and verification steps
3. **Consistent environment**: Same build process for all architectures
4. **Resource optimization**: Configurable parallelism based on available resources
5. **Enhanced testing**: More comprehensive validation of the built modules

By using this unified Docker build system, developers can more easily work with the Diplomacy Cicero codebase across different environments and platforms.

## Cross-Platform Testing

The project includes a script for building and testing the Docker image across multiple platforms:

```bash
# Basic cross-platform testing
./scripts/test_cross_platform.sh

# With custom options
./scripts/test_cross_platform.sh --version 1.0.0 --registry yourorg
```

This script:

1. Uses Docker buildx to build multi-platform images
2. Tests the image on your native architecture
3. Uses QEMU to test on non-native architectures (if available)
4. Provides detailed output about platform compatibility

To enable full cross-platform testing:

```bash
# Install QEMU (Ubuntu)
sudo apt-get install qemu binfmt-support qemu-user-static

# Install QEMU (macOS)
brew install qemu

# Set up the QEMU emulation handlers
docker run --privileged --rm tonistiigi/binfmt --install all
```

The cross-platform testing is essential to ensure that the unified Docker build works correctly on both x86_64 (Intel/AMD) and ARM64 (Apple Silicon, AWS Graviton) architectures.