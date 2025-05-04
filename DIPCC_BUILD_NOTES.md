# Building the Diplomacy Cicero C++ Components (dipcc)

This document provides detailed information about building the C++ components of the Diplomacy Cicero project, specifically the dipcc module which powers the core game logic.

> **Note:** For a detailed explanation of how the dipcc C++ library integrates with the Python codebase through fairdiplomacy.pydipcc, see [docs/dipcc_integration.md](docs/dipcc_integration.md) and [docs/module_dependencies.md](docs/module_dependencies.md).

## Directory Structure

The dipcc C++ code has a nested directory structure:

- `dipcc/`: Top-level directory
  - `dipcc/cc/`: C++ implementation files
  - `dipcc/pybind/`: Python binding code
  - `dipcc/profiling/`: Profiling utilities
  - `dipcc/python/`: Python module structure

## Build Requirements

- GCC 9.4+ with C++17 support
- CMake 3.10+
- Python 3.7+
- pybind11 library
- Protocol Buffers 3.19.1 (exact version)
- PyTorch libraries

## Build Process

The build process involves several steps that must be performed in the correct order:

1. **Install system dependencies**

   ```bash
   apt-get update && apt-get install -y \
       build-essential cmake gcc-9 g++-9 python3.8-dev \
       libgoogle-glog-dev pybind11-dev
   ```

2. **Configure compiler alternatives**

   ```bash
   update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-9 90
   update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-9 90
   update-alternatives --install /usr/bin/cc cc /usr/bin/gcc-9 90
   update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++-9 90
   ```

3. **Install Python dependencies**

   ```bash
   pip install pybind11 numpy torch
   ```

4. **Build the C++ library**

   ```bash
   cd dipcc
   mkdir -p build && cd build
   pybind11_DIR=$(python3 -c "import pybind11; print(pybind11.get_cmake_dir())")
   cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=$pybind11_DIR ..
   make -j2 pydipcc
   ```

5. **Create the necessary Python module structure**

   ```bash
   mkdir -p /path/to/fairdiplomacy
   cp /path/to/dipcc/build/dipcc/python/pydipcc*.so /path/to/fairdiplomacy/
   ```

6. **Configure the Python import**

   Create a `fairdiplomacy/__init__.py` file with the following content:

   ```python
   #!/usr/bin/env python
   import sys, os
   import importlib.util

   # Make the pydipcc module available
   spec = importlib.util.spec_from_file_location(
       "pydipcc", 
       os.path.join(os.path.dirname(__file__), "pydipcc.cpython-XX-ARCH-OS.so")
   )
   if spec:
       pydipcc = importlib.util.module_from_spec(spec)
       spec.loader.exec_module(pydipcc)
       sys.modules["fairdiplomacy.pydipcc"] = pydipcc
   ```

## Common Issues and Solutions

### 1. Nested Directory Structure

The repository has a nested structure where C++ files are in `dipcc/dipcc/cc/` instead of `dipcc/cc/`. This can cause issues with CMake finding the correct files. To fix this:

```bash
mkdir -p /path/to/dipcc/cc /path/to/dipcc/pybind
cp -r /path/to/dipcc/dipcc/cc/* /path/to/dipcc/cc/
cp -r /path/to/dipcc/dipcc/pybind/* /path/to/dipcc/pybind/
cp -r /path/to/dipcc/dipcc/profiling /path/to/dipcc/
```

### 2. pybind11 Not Found

If CMake cannot find pybind11, set the pybind11_DIR environment variable:

```bash
pybind11_DIR=$(python3 -c "import pybind11; print(pybind11.get_cmake_dir())")
export pybind11_DIR
```

### 3. Python Linking Issues

If you encounter Python linking errors in the build process:

```
undefined reference to `PyErr_SetString'
undefined reference to `_Py_Dealloc'
```

Make sure your build system is properly linking against the Python libraries. The CMakeLists.txt should include:

```cmake
find_package(PythonInterp 3 REQUIRED)
find_package(PythonLibs 3 REQUIRED)
include_directories(${PYTHON_INCLUDE_DIRS})
```

### 4. Memory Issues During Compilation

The C++ compilation can be memory-intensive. If you're running out of memory during the build:

```bash
# Limit compilation to a smaller number of parallel jobs
make -j2 pydipcc
```

## Testing the Build

To test if the build was successful, you can run a simple Python script:

```python
import sys
sys.path.insert(0, "/path/to/project")

from fairdiplomacy import pydipcc
print("pydipcc imported successfully")

game = pydipcc.Game()
print("Game created successfully")
print("Current phase:", game.get_current_phase())
```

## Available API Methods

Successfully imported pydipcc module will have the following components:

- `pydipcc.Game`: Main game class for representing and manipulating Diplomacy games
- `pydipcc.PhaseData`: Class representing data for a single game phase
- `pydipcc.CFRStats` and `pydipcc.SinglePowerCFRStats`: For counterfactual regret minimization
- `pydipcc.ThreadPool`: For parallel processing
- Various utility functions for encoding and decoding game states

## Docker Build

To build dipcc in a Docker container, the Dockerfile includes all the necessary dependencies and build steps. We provide two Dockerfiles:

- `Dockerfile`: Streamlined build for production use
- `Dockerfile.phased`: Detailed step-by-step build with testing at each phase (useful for debugging)

### Using Docker Compose (Recommended)

The easiest way to use the Docker environment is with Docker Compose:

```bash
# Build and start the container
docker-compose up -d

# Access the running container
docker-compose exec diplomacy bash

# Test if dipcc is working correctly
docker-compose exec diplomacy python /app/test_pydipcc.py
```

### Manual Docker Usage

You can also build and run the Docker container manually:

```bash
# Build the main Docker image
docker build -t diplomacy_cicero .

# Run the container with the current directory mounted
docker run -it -v $(pwd):/app diplomacy_cicero bash

# For debugging: build the phased version
docker build -t diplomacy_cicero_phased -f Dockerfile.phased .
docker run -it diplomacy_cicero_phased bash
```

### Verifying the Build

Once inside the Docker container, you can test if the dipcc build was successful:

```bash
# Run the test script
python /app/test_pydipcc.py

# Or try importing and using the module directly
python -c "from fairdiplomacy import pydipcc; game = pydipcc.Game(); print(game.get_state())"
```