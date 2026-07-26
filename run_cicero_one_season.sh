#!/bin/bash
# Script to run Cicero playing as Turkey for one season

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

# Check for model files for informational purposes
echo "Checking for model files in /app/models..."
MODEL_FILES=$(docker-compose exec diplomacy bash -c "cd /app && ls -l models/ 2>/dev/null || echo 'No models directory found'")
echo "Model files:"
echo "$MODEL_FILES"

# Install ParlAI if not already installed
echo "Checking if ParlAI is installed..."
docker-compose exec diplomacy bash -c "python -c 'import parlai' 2>/dev/null || (echo 'Installing ParlAI...' && cd /app && ./scripts/install_parlai.sh)"

# Run with Cicero agent
echo "Starting game with Cicero as Turkey..."
docker-compose exec diplomacy python run.py --adhoc \
  --cfg conf/c01_ag_cmp/cmp.prototxt \
  Iagent_one=agents/cicero.prototxt \
  Iagent_six=agents/ablations/cicero_imitation_only.prototxt \
  power_one=TURKEY \
  num_trials=1 \
  seed=42 \
  max_years=1  # Only run for one year (3 phases: Spring, Fall, Winter)

echo "Game completed for one year."
echo "Results should be saved in the experiment directory (shown in output)."