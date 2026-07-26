# Running Cicero as Turkey

This document explains how to run Cicero (the FAIR/Meta Diplomacy AI) playing as Turkey using Docker.

## Prerequisites

1. Docker installed and running on your system
2. The repository cloned to your local machine
3. Docker image built using `./scripts/docker_build.sh`

## Available Scripts

Two scripts are provided for running different versions of the Turkey gameplay:

### 1. Full Cicero Agent (run_cicero_turkey.sh)

This script runs the full Cicero AI agent as Turkey against six imitation agents using the proper configuration framework. This demonstrates the recommended approach using the run.py script with protobuf configs.

```bash
./run_cicero_turkey.sh
```

**Note**: This requires model files to be downloaded first. Inside the container, run:
```bash
bash bin/download_model_files.sh dbEmG*yo@fuWzb79cx_pN7.TRm4cqk
```

### 2. Simple Game Engine Demo (run_simple_turkey.sh)

This script runs a simplified game where Turkey is controlled by a basic strategy using only the core game engine. This doesn't use any of the AI models but demonstrates the basic game mechanics.

```bash
./run_simple_turkey.sh
```

## How It Works

Both scripts:
1. Check if Docker is running
2. Ensure the Docker container is started
3. Run the appropriate Python script inside the container
4. Display the output and results

## Viewing Results

For the full Cicero agent, results are saved in an experiment directory which is shown in the output.

For the simple game engine demo, results are saved to `/tmp/simple_turkey_game.json` inside the container. You can view it with:

```bash
docker-compose exec diplomacy cat /tmp/simple_turkey_game.json
```

## Troubleshooting

- If you encounter "Error: Docker is not running", start Docker Desktop or the Docker service on your system.
- If model files are missing, follow the instructions to download them using the script provided in the bin directory.
- If you see memory-related errors, try increasing the memory allocation in your Docker settings.

## Additional Resources

For more information, refer to:
- README.md - Main project documentation
- DOCKER_GUIDE.md - Guide for using Docker with this codebase
- DOCKER_USAGE.md - Instructions for development in the Docker environment