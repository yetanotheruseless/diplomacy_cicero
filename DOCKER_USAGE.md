# Docker Environment for Diplomacy Cicero

This document provides guidance on using the Docker environment for development and exploration of the Diplomacy Cicero codebase.

## Getting Started

### Requirements
- Docker installed and running
- Git repository cloned locally

### Building the Docker Image
```bash
./scripts/docker_build.sh
```

### Starting a Container
```bash
./scripts/docker_run.sh
```

This will start an interactive shell inside the container where you can work with the codebase.

## Working with the Code

The Docker environment provides several advantages:
- Consistent environment across different platforms
- All necessary system dependencies installed
- Isolated environment that doesn't affect your host system

### Current Limitations

The current Docker setup has some limitations:
- Some protobuf import issues when using the existing generated files
- Not all dependencies are installed (e.g., full PyTorch installation)

### Recommended Workflow

#### 1. Exploring the Codebase
You can explore the codebase directly in the container:
```bash
ls -la                    # List all files
cd fairdiplomacy          # Navigate to the core library
cd parlai_diplomacy       # Navigate to the dialogue components
```

#### 2. Running Tests
Basic tests can be run in the container:
```bash
python -m pytest unit_tests/test_utils_game.py  # Run a specific test
```

#### 3. Protobuf Compilation
You can compile protobuf definitions in the container:
```bash
make protos_basic         # Compile protobuf schemas
```

#### 4. Building Your Own Components
You can create and test your own components:
```bash
# Create a new Python file
python -c "print('Hello from Docker!')"
```

## Troubleshooting

### Protobuf Import Issues
If you encounter issues with protobuf imports, you can:
1. Work with the Docker environment for exploration
2. Use the conda-based setup on a Linux system for full functionality
3. Create minimal protobuf definitions for testing

### Docker Container Management
```bash
# List running containers
docker ps

# Stop a container
docker stop <container_id>

# Remove all stopped containers
docker-compose down
```

## Next Steps

For full functionality, consider:
1. Using a Linux-based system with the original installation method
2. Building specific components in the Docker environment
3. Contributing fixes to make the system more portable

The Docker environment provides a good starting point for exploring the codebase, even if some components require additional setup for full functionality.