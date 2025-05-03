#!/bin/bash
# Script to build the Docker image for Diplomacy Cicero

echo "Building Docker image for Diplomacy Cicero..."
docker-compose build

echo "Docker image built successfully."
echo "To start a container, run: ./scripts/docker_run.sh"