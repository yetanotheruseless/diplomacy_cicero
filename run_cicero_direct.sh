#!/bin/bash
# Script to run Cicero playing as Turkey in the Docker container (simplified version)

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

# Run the Cicero agent directly using the commands from the README
echo "Running Cicero as Turkey in the Docker container..."
echo "This will run Cicero against imitation agents using the recommended configuration."
echo "Note: This may fail if model files are not downloaded."

# Run the direct command inside the container
docker-compose exec diplomacy bash -c "cd /app && python run.py --adhoc --cfg conf/c01_ag_cmp/cmp.prototxt Iagent_one=agents/cicero.prototxt Iagent_six=agents/ablations/cicero_imitation_only.prototxt power_one=TURKEY num_trials=1 seed=42"

echo "Script completed."
echo "If the above command failed due to missing model files, run the following inside the container:"
echo "bash bin/download_model_files.sh dbEmG*yo@fuWzb79cx_pN7.TRm4cqk"