#!/bin/bash
# Script to test basic functionality in the Docker container

echo "Testing Docker container setup for Diplomacy Cicero..."
docker-compose run --rm diplomacy bash -c "cd /app && \
echo 'Testing protobuf import...' && \
python -c 'from conf import conf_pb2; print(\"✅ Protobuf module loaded successfully\")' && \
echo '------------------------' && \
echo 'Testing directory structure...' && \
ls -la && \
echo '------------------------' && \
echo 'Showing available proto modules:' && \
ls -la conf/*pb2.py && \
echo '------------------------' && \
echo 'All basic tests completed successfully!'"