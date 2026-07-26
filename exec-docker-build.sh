#!/bin/bash
# Script to copy build script into Docker and execute it

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

# Copy build script to the container
echo "Copying build script to the Docker container..."
docker cp docker-build-cicero.sh $(docker-compose ps -q diplomacy):/app/docker-build-cicero.sh

# Make the script executable in the container
echo "Making the script executable..."
docker-compose exec diplomacy chmod +x /app/docker-build-cicero.sh

# Run the script in the container
echo "Running the build script in the Docker container..."
docker-compose exec diplomacy /app/docker-build-cicero.sh

echo "Build process complete."
echo "You can now run: ./run_simple_turkey.sh"