#!/bin/bash
# Script to build Docker image and regenerate protobuf files

echo "Building Docker image for Diplomacy Cicero with fresh protobuf generation..."
docker-compose build --no-cache

echo "Verifying environment versions match README requirements..."
docker-compose run --rm diplomacy bash -c "
    echo 'Python version:' && python --version && 
    echo 'GCC version:' && gcc --version && 
    echo 'CMake version:' && cmake --version && 
    echo 'Protobuf version:' && pip show protobuf | grep Version
"

echo "Testing protobuf functionality..."
docker-compose run --rm diplomacy python scripts/test_protobuf.py

echo "Testing codebase protobuf files..."
docker-compose run --rm diplomacy bash -c "
    cd /app && 
    echo -e 'import sys\nfrom conf import conf_pb2\nprint(\"Codebase protobuf files imported successfully\")' > test_import.py && 
    python test_import.py || (
        echo 'Running protobuf fixes...' && 
        python scripts/fix_protos.py && 
        python test_import.py && 
        echo 'Protobuf fixes successfully applied' || 
        echo 'Error: Protobuf fixes did not resolve the import issue'
    )
"

echo "Testing import of all main protobuf modules..."
docker-compose run --rm diplomacy bash -c "
    cd /app && 
    echo -e '
import sys
try:
    from conf import conf_pb2, agents_pb2, common_pb2, misc_pb2
    print(\"All main protobuf modules imported successfully\")
    # Test creating a simple message
    msg = conf_pb2.Config()
    print(\"Successfully created a protobuf message\")
except Exception as e:
    print(f\"Error importing protobuf modules: {e}\")
    sys.exit(1)
' > test_all_protos.py && 
    python test_all_protos.py
"

echo "Running comprehensive Docker environment check..."
docker-compose run --rm diplomacy python scripts/check_docker_environment.py

echo "Docker build complete. Use ./scripts/docker_run.sh to start a container."