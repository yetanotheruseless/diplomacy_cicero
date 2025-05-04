# Docker Release Process for Diplomacy Cicero

This document outlines the process for creating, tagging, and releasing Docker images for the Diplomacy Cicero project.

## Release Workflow

The Docker release process involves the following steps:

1. Build and test Docker images for various platforms
2. Tag images with appropriate version numbers
3. Push images to a container registry
4. Update documentation and references

## Version Naming Convention

We use semantic versioning (SemVer) for Docker image tags:

```
diplomacy_cicero:[version]-[arch]-[build]
```

Where:
- `version`: Follows the format `major.minor.patch` (e.g., `1.0.0`)
- `arch`: CPU architecture (`x86_64` or `arm64`)
- `build`: Build type (`full` or `minimal`)

Examples:
- `diplomacy_cicero:1.0.0-x86_64-full`
- `diplomacy_cicero:1.0.0-arm64-minimal`

The `latest` tag should always point to the most recent stable release.

## Build Types

We provide two build types:

1. **Full**: Includes all dependencies and model weights
2. **Minimal**: Includes only the core components without model weights

## Build Process

1. **Prepare Environment**

   ```bash
   # Checkout the appropriate release branch or tag
   git checkout v1.0.0
   
   # Create a build directory for the release
   mkdir -p release
   ```

2. **Build Images for Different Architectures**

   ```bash
   # For x86_64 architecture (Intel/AMD)
   ./scripts/docker_build.sh --jobs 4 --tag "1.0.0-x86_64-full"
   
   # For ARM64 architecture (Apple Silicon/AWS Graviton)
   ./scripts/docker_build.sh --jobs 4 --tag "1.0.0-arm64-full"
   ```

3. **Test Images**

   ```bash
   # Run validation tests on the built image
   docker run --rm diplomacy_cicero:1.0.0-x86_64-full python /app/test_pydipcc.py
   docker run --rm diplomacy_cicero:1.0.0-x86_64-full make test_fast
   ```

4. **Create Manifests for Multi-Architecture Support**

   ```bash
   # Create and push the manifest for the release version
   docker manifest create diplomacy_cicero:1.0.0 \
     diplomacy_cicero:1.0.0-x86_64-full \
     diplomacy_cicero:1.0.0-arm64-full
   
   docker manifest push diplomacy_cicero:1.0.0
   
   # Update the latest tag
   docker manifest create diplomacy_cicero:latest \
     diplomacy_cicero:1.0.0-x86_64-full \
     diplomacy_cicero:1.0.0-arm64-full
   
   docker manifest push diplomacy_cicero:latest
   ```

## Release Checklist

Before releasing a new Docker image:

- [ ] Ensure all tests pass
- [ ] Verify the module loading works on all target architectures
- [ ] Check that the image size is reasonable
- [ ] Validate the protobuf compilation
- [ ] Test model weight downloading and integration
- [ ] Update documentation with new version information

## Docker Hub Integration

To push images to Docker Hub:

1. **Login to Docker Hub**

   ```bash
   docker login
   ```

2. **Tag Images for Docker Hub**

   ```bash
   docker tag diplomacy_cicero:1.0.0-x86_64-full yourorg/diplomacy_cicero:1.0.0-x86_64-full
   docker tag diplomacy_cicero:1.0.0-arm64-full yourorg/diplomacy_cicero:1.0.0-arm64-full
   ```

3. **Push Images**

   ```bash
   docker push yourorg/diplomacy_cicero:1.0.0-x86_64-full
   docker push yourorg/diplomacy_cicero:1.0.0-arm64-full
   ```

4. **Create and Push Manifests**

   ```bash
   docker manifest create yourorg/diplomacy_cicero:1.0.0 \
     yourorg/diplomacy_cicero:1.0.0-x86_64-full \
     yourorg/diplomacy_cicero:1.0.0-arm64-full
   
   docker manifest push yourorg/diplomacy_cicero:1.0.0
   ```

## GitHub Container Registry Integration

To use GitHub Container Registry instead:

1. **Login to GitHub Container Registry**

   ```bash
   echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_USERNAME --password-stdin
   ```

2. **Tag Images for GitHub Container Registry**

   ```bash
   docker tag diplomacy_cicero:1.0.0-x86_64-full ghcr.io/yourorg/diplomacy_cicero:1.0.0-x86_64-full
   docker tag diplomacy_cicero:1.0.0-arm64-full ghcr.io/yourorg/diplomacy_cicero:1.0.0-arm64-full
   ```

3. **Push Images**

   ```bash
   docker push ghcr.io/yourorg/diplomacy_cicero:1.0.0-x86_64-full
   docker push ghcr.io/yourorg/diplomacy_cicero:1.0.0-arm64-full
   ```

## Automation with GitHub Actions

For automated builds and releases, you can set up GitHub Actions workflows. Here's a sample workflow file:

```yaml
name: Docker Release

on:
  release:
    types: [published]

jobs:
  build-and-push:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, self-hosted-arm64]
        build-type: [full, minimal]
    
    steps:
      - name: Checkout
        uses: actions/checkout@v2
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v1
      
      - name: Login to GitHub Container Registry
        uses: docker/login-action@v1
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v3
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
      
      - name: Determine architecture
        id: arch
        run: |
          if [ "${{ matrix.os }}" = "ubuntu-latest" ]; then
            echo "::set-output name=arch::x86_64"
          else
            echo "::set-output name=arch::arm64"
          fi
      
      - name: Build and push
        uses: docker/build-push-action@v2
        with:
          context: .
          file: Dockerfile.unified
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ steps.meta.outputs.version }}-${{ steps.arch.outputs.arch }}-${{ matrix.build-type }}
          build-args: |
            DIPCC_BUILD_JOBS=4
```

## Troubleshooting Release Issues

### Common Issues

1. **Missing Dependencies in Docker Images**

   If dependencies are missing, update the Dockerfile:

   ```bash
   # Add missing dependencies
   RUN apt-get update && apt-get install -y \
       missing-package-1 \
       missing-package-2
   ```

2. **Platform Compatibility Issues**

   Ensure proper cross-compilation flags are set for ARM64 builds:

   ```bash
   # Add platform-specific compiler flags
   ENV CFLAGS="-march=armv8-a"
   ```

3. **Model Weight Integration**

   If model weights aren't being downloaded:

   ```bash
   # Test the model weight downloader
   docker run --rm diplomacy_cicero:1.0.0 bash bin/download_model_files.sh <PASSWORD>
   ```

## Resource Requirements

Different versions of the Docker image have different resource requirements:

| Version | CPU Cores | RAM | Disk Space |
|---------|-----------|-----|------------|
| Full    | 4+        | 8GB+ | 20GB+      |
| Minimal | 2+        | 4GB+ | 5GB+       |

## Release Notes Template

When publishing a new release, use this template for the release notes:

```markdown
# Diplomacy Cicero Docker Release v1.0.0

## Images
- `diplomacy_cicero:1.0.0-x86_64-full` - Full version for x86_64
- `diplomacy_cicero:1.0.0-arm64-full` - Full version for ARM64
- `diplomacy_cicero:1.0.0-x86_64-minimal` - Minimal version for x86_64
- `diplomacy_cicero:1.0.0-arm64-minimal` - Minimal version for ARM64

## Changes
- [List major changes in this release]

## System Requirements
- [Document resource requirements]

## Installation
```bash
docker pull ghcr.io/yourorg/diplomacy_cicero:1.0.0
```

## Known Issues
- [Document any known issues]
```

## Conclusion

Following this release process will ensure consistent, reliable Docker image releases for the Diplomacy Cicero project. The multi-architecture support will allow users to run the project on various hardware platforms, and the versioning scheme will help users track and use specific releases.