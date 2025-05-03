#!/bin/bash
# Script to test minimal functionality in Docker

echo "Running minimal test in Docker container..."
docker-compose run --rm diplomacy bash -c "
    cd /app && 
    echo 'import sys; print(\"Python version:\", sys.version)' > test.py && 
    python test.py && 
    echo 'import protobuf; print(\"Protobuf version:\", protobuf.__version__)' > test_protobuf.py || 
    echo 'from google import protobuf; print(\"Protobuf version:\", protobuf.__version__)' > test_protobuf.py && 
    python test_protobuf.py || echo 'Protobuf import failed, but we can still use basic Python' &&
    echo 'Creating minimal protobuf definition...' &&
    echo 'syntax = \"proto3\";' > test.proto &&
    echo 'message Test {' >> test.proto &&
    echo '  string name = 1;' >> test.proto &&
    echo '}' >> test.proto &&
    echo 'Compiling minimal protobuf definition...' &&
    protoc test.proto --python_out=. &&
    echo 'Testing minimal protobuf import...' &&
    python -c 'import test_pb2; print(\"Minimal protobuf test successful\")' || echo 'Minimal protobuf test failed'
"