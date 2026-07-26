#!/bin/bash
# Script to build Diplomacy Cicero properly in the Docker container

# Set safe shell options
set -e  # Exit on any error
set -o pipefail

# Print header
echo "====================================================="
echo " BUILDING DIPLOMACY CICERO IN DOCKER"
echo "====================================================="
echo "Python version: $(python --version)"
echo "Pip version: $(pip --version)"

# Update pip and setuptools first
echo "Updating pip and setuptools..."
pip install --upgrade pip setuptools wheel

# Step 1: Install required Python dependencies
echo "Step 1: Installing critical Python dependencies..."
pip install pybind11==2.6.2 numpy==1.20.3 cython==0.29.24 joblib==1.1.0 tqdm==4.62.1

# Step 2: Install minimal subset of requirements for the simple game
echo "Step 2: Installing minimal requirements for the game engine..."
pip install setuptools==59.5.0 wheel==0.37.1 attrs==20.2.0

# Step 3: Build just the C++ game engine (dipcc) without the selfplay components
echo "Step 3: Building the C++ game engine (dipcc)..."
cd /app/dipcc

# Clean up any previous failed builds
rm -rf build
mkdir -p build
cd build

# Configure with minimal features and memory optimization
echo "Configuring CMake for minimal build..."
pybind11_DIR=$(python -c "import pybind11; print(pybind11.get_cmake_dir())")
CXXFLAGS="-Os" cmake -DCMAKE_BUILD_TYPE=MinSizeRel \
    -DBUILD_TESTS=OFF \
    -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_PREFIX_PATH=$pybind11_DIR \
    ..

# Build with less memory usage (just 1 job)
echo "Building pydipcc with 1 job to avoid memory issues..."
make -j1 pydipcc

# Copy the resulting module to the right location
echo "Copying pydipcc module to fairdiplomacy directory..."
cp dipcc/python/pydipcc*.so /app/fairdiplomacy/
echo "✅ Successfully built pydipcc module!"

# Step 4: Compile protocol buffers
echo "Step 4: Compiling protocol buffers..."
cd /app
make protos_basic

# Patch the protocol buffer files
echo "Patching protobuf files..."
python heyhi/bin/patch_protos.py conf/*pb2.py

# Step 5: Verify the installation
echo "Step 5: Verifying the installation..."
echo "Testing pydipcc module..."
python /app/test_pydipcc.py

echo ""
echo "====================================================="
echo " BUILD COMPLETED SUCCESSFULLY"
echo "====================================================="
echo ""
echo "You can now run the simple game with:"
echo "  python play_turkey_correct.py --phases 3 --power TURKEY"
echo ""
echo "To run the full Cicero agent, you would need to download the model weights with:"
echo "  bash bin/download_model_files.sh <PASSWORD>"
echo "  (Password is in the README: dbEmG*yo@fuWzb79cx_pN7.TRm4cqk)"
echo ""
echo "Note: The selfplay component was not built, so some advanced features"
echo "      may not work, but the core game engine is functional."