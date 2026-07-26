# Using Docker with Diplomacy Cicero

> **On an Apple-Silicon Mac?** Use **[README_MACOS.md](./README_MACOS.md)** — a
> verified, end-to-end walkthrough (build + run the full Cicero agent on arm64
> via Docker). The notes below are the older, generic Docker docs.

## IMPORTANT: Docker Required

The Diplomacy Cicero codebase **requires** Docker for reliable operation across different platforms. The codebase uses platform-specific C++ libraries and exact dependency versions that are difficult to manage consistently outside of a container.

## Quick Start

1. **Build the Docker image**:
   ```bash
   ./scripts/docker_build.sh
   ```

2. **Run the container**:
   ```bash
   ./scripts/docker_run.sh
   ```

3. **Verify the installation** (inside the container):
   ```bash
   ./scripts/verify_full_build.sh
   ```

4. **Run a test game** (inside the container):
   ```bash
   python run.py --adhoc --cfg conf/c01_ag_cmp/cmp.prototxt \
     Iagent_one=agents/cicero.prototxt \
     Iagent_six=agents/ablations/cicero_imitation_only.prototxt \
     power_one=TURKEY
   ```

## Safely Running Commands in Docker

We've provided a helper script to ensure commands run inside the Docker container:

```bash
# Run any command inside the Docker container
./scripts/run_in_docker.sh python test_pydipcc.py

# Another example
./scripts/run_in_docker.sh ./scripts/verify_full_build.sh --full-test
```

## Docker Configuration

The Docker container is configured in:
- `Dockerfile.unified`: The main Dockerfile
- `docker-compose.yml`: Container orchestration with resource limits
- `scripts/docker_build.sh`: Script to build the image
- `scripts/docker_run.sh`: Script to run the container

## Memory Requirements

The Docker container requires substantial memory, especially during the build process:

1. **Building the container**: Minimum 4GB, recommended 8GB
2. **Running the container**: Minimum 4GB, recommended 8GB

In `docker-compose.yml`, we've set:
```yaml
deploy:
  resources:
    limits:
      memory: 8G
    reservations:
      memory: 4G
```

Adjust these values based on your system's available memory.

## Troubleshooting

### Build Failures

If the build fails with memory errors, reduce parallel jobs:
1. Edit `docker-compose.yml`
2. Change `DIPCC_BUILD_JOBS` to `1`
3. Rebuild with `./scripts/docker_build.sh`

### Module Import Errors

If you encounter module import errors inside the container:
1. Run `python test_scripts/verify_imports.py` to diagnose
2. Check if `pydipcc.so` exists: `find / -name "pydipcc*.so"`
3. Verify protobuf modules: `python -c "from conf import conf_pb2; print('OK')"`

### Cross-Platform Issues

The Unified Dockerfile has been designed to work on both x86_64 and ARM64 architectures:
- It dynamically detects and loads the appropriate shared library
- Memory optimizations are applied for both architectures
- Build flags are adjusted based on platform needs

## Running Without Docker (Not Recommended)

If you must run without Docker (strongly discouraged):
1. See `DIPCC_BUILD_NOTES.md` for manual build instructions
2. Requires exact versions: Python 3.8, protobuf 3.19.1, GCC 9.4+
3. May encounter platform-specific issues that are difficult to diagnose

For any issues, please use Docker as the reference environment.