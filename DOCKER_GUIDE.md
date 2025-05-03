# Docker Guide for Diplomacy Cicero

This guide explains how to use Docker to work with the Diplomacy Cicero codebase.

## Prerequisites

- Docker installed and running on your system
  - [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
  - [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
  - [Docker Engine for Linux](https://docs.docker.com/engine/install/)

## Building the Docker Image

1. Make sure Docker is running (you should see the Docker icon in your system tray or menubar)

2. Run the build script:
   ```bash
   ./scripts/docker_build.sh
   ```

   This will:
   - Build a Docker image using the `Dockerfile`
   - Install all necessary dependencies
   - Set up the Python environment
   - Prepare the codebase for use

   Expected output:
   ```
   Building Docker image for Diplomacy Cicero...
   [+] Building ...
   ... [build logs] ...
   Docker image built successfully.
   To start a container, run: ./scripts/docker_run.sh
   ```

   Note: The first build will take some time as it downloads the Ubuntu image and installs dependencies.

## Running the Docker Container

1. After building the image, start a container:
   ```bash
   ./scripts/docker_run.sh
   ```

   This will:
   - Start a new container with the built image
   - Mount your local code directory into the container
   - Mount a persistent volume for model files
   - Drop you into a bash shell in the container

   Expected output:
   ```
   Starting Docker container for Diplomacy Cicero...
   root@container:/app#
   ```

2. Once inside the container, you can:
   - Run the tests: `make test_fast`
   - Compile the code: `make compile`
   - Download model files: `bash bin/download_model_files.sh <PASSWORD>`
   - Run simulations: `python run.py --adhoc ...`

## Working with the Container

- Your local code directory is mounted inside the container at `/app`
- Any changes you make to the code on your host machine will be immediately visible in the container
- Model files are stored in a persistent Docker volume so they won't be lost when the container stops

## Stopping the Container

- To exit the container, type `exit` or press `Ctrl+D`
- The container will stop when you exit

## Troubleshooting

If you see this error:
```
Cannot connect to the Docker daemon... Is the docker daemon running?
```

Make sure Docker Desktop or the Docker service is running on your system.

---

With this Docker setup, you can develop code on your local machine using your preferred editor/IDE, while running the code in a consistent Ubuntu-based environment that has all the necessary dependencies properly installed.