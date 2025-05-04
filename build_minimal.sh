#!/bin/bash
# Build the absolute minimum to get the game engine working

echo "Starting minimal build with aggressive memory optimizations..."

# Clean up previous build
echo "Cleaning previous builds..."
rm -rf build/
cd dipcc && rm -rf build/ && cd ..

# Create a minimal build configuration
echo "Configuring minimal build..."
cd dipcc && mkdir -p build && cd build
CXXFLAGS="-Os" cmake -DCMAKE_BUILD_TYPE=MinSizeRel \
      -DBUILD_TESTS=OFF \
      -DBUILD_SHARED_LIBS=ON \
      ..

# Build with absolute minimum settings
echo "Building with minimal memory usage (this may take a while)..."
make -j1 pydipcc

# Check if build succeeded
if [ $? -ne 0 ]; then
    echo "Build failed. Let's try even more minimal build..."
    # Try with even more aggressive memory saving
    make clean
    CXXFLAGS="-Os -g0" cmake -DCMAKE_BUILD_TYPE=MinSizeRel -DBUILD_TESTS=OFF ..
    make -j1 VERBOSE=1 pydipcc
fi

# Copy the resulting library if it exists
echo "Checking for built libraries..."
find . -name "*.so"

# Try to copy any .so files found
mkdir -p /app/fairdiplomacy
find . -name "*.so" -exec cp {} /app/fairdiplomacy/ \;

# Create a test script
cd /app
echo "Creating test script..."
cat > test_dipcc_basic.py << 'EOT'
print("Looking for dipcc module...")

# Try multiple paths
import sys
import glob
import os

# Add potential paths
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/dipcc/build/dipcc/python")
sys.path.insert(0, "/app/dipcc/build/out")

# Print Python path
print("Python path:", sys.path)

# Look for .so files
print("Looking for .so files...")
so_files = []
for path in ["/app/fairdiplomacy", "/app/dipcc/build", "/app/dipcc/build/dipcc/python"]:
    if os.path.exists(path):
        so_files.extend(glob.glob(f"{path}/*.so"))
        so_files.extend(glob.glob(f"{path}/**/*.so"))

print(f"Found .so files: {so_files}")

# Try to import
try:
    print("Trying to import fairdiplomacy.pydipcc...")
    from fairdiplomacy import pydipcc
    print("Successfully imported fairdiplomacy.pydipcc")
    print("Available in pydipcc:", dir(pydipcc))
except ImportError as e:
    print(f"ImportError with fairdiplomacy.pydipcc: {e}")
    
    try:
        print("Trying to import dipcc directly...")
        import dipcc
        print("Successfully imported dipcc")
        print("Available in dipcc:", dir(dipcc))
    except ImportError as e:
        print(f"ImportError with dipcc: {e}")
        
        # Try to load directly from .so file if any were found
        if so_files:
            print(f"Trying to load directly from .so file: {so_files[0]}")
            import importlib.util
            spec = importlib.util.spec_from_file_location("direct_pydipcc", so_files[0])
            if spec:
                direct_pydipcc = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(direct_pydipcc)
                print("Loaded module directly:", dir(direct_pydipcc))
            else:
                print("Failed to create module spec from .so file")
        else:
            print("No .so files found to load directly")
EOT

echo "Running test script..."
python test_dipcc_basic.py