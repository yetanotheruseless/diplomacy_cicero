#!/bin/bash
# Script to run the build script inside the Docker container

# Make sure Docker is running
echo "Checking Docker status..."
if ! docker ps > /dev/null 2>&1; then
  echo "Error: Docker is not running. Please start Docker and try again."
  exit 1
fi

# Ensure the container is running
if ! docker-compose ps | grep "diplomacy" | grep "Up" > /dev/null; then
  echo "Starting Docker container..."
  docker-compose up -d
fi

# Copy the build script into the container and run it
echo "Running the build script inside the Docker container..."
docker-compose exec diplomacy bash -c "cd /app && ./docker-build-cicero.sh"

echo "Script completed!"
echo "You can now run the simple Turkey game in Docker with: ./run_simple_turkey.sh"