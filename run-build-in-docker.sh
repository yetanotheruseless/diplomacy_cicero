#!/bin/bash
# Script to run the build script in the Docker container

# Make sure Docker is running
echo "Checking Docker status..."
if ! docker ps > /dev/null 2>&1; then
  echo "Error: Docker is not running. Please start Docker and try again."
  exit 1
fi

# Check if the container is already running
if ! docker-compose ps | grep "diplomacy" | grep "Up" > /dev/null; then
  echo "Starting Docker container..."
  docker-compose up -d
fi

# Make the script executable
chmod +x docker-build-cicero.sh

# Run the build script in the container
echo "Running the build script in the Docker container..."
docker-compose exec diplomacy ./docker-build-cicero.sh

echo "Build process complete."
echo "You can now run: ./run_simple_turkey.sh"