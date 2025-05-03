#!/bin/bash
# Script to run a Docker container for Diplomacy Cicero

echo "Starting Docker container for Diplomacy Cicero..."
docker-compose run --service-ports --rm diplomacy bash -c "cd /app && echo 'Diplomacy Cicero container ready.' && echo 'You can now run commands like: python -c \"from conf import conf_pb2; print(\\\"Protobuf module loaded successfully\\\")\"' && exec bash"
echo "Container has been stopped."