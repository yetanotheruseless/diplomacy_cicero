#!/bin/bash
# Script to run a simple Turkey game using the core engine in Docker

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

# Run the play_turkey_correct.py script inside the container
echo "Running simple Turkey gameplay in the Docker container..."
docker-compose exec diplomacy python play_turkey_correct.py --phases 3 --power TURKEY --save /tmp/simple_turkey_game.json

echo "Script completed."
echo "The game state was saved to /tmp/simple_turkey_game.json inside the container."
echo "To view it, run: docker-compose exec diplomacy cat /tmp/simple_turkey_game.json"