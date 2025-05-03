# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Environment
- **Recommended setup**: Use Docker (works on all platforms)
  - Build image: `./scripts/docker_build.sh`
  - Run container: `./scripts/docker_run.sh`
- Alternative conda setup: `./scripts/setup_conda_env.sh` (not recommended on macOS)
- Alternative venv setup: `./scripts/setup_env.sh` (uses uv) or `./scripts/setup_env_pip.sh` (uses pip)
- **Note**: This project was primarily developed for Linux/Ubuntu. Docker provides the most reliable environment.

## System Requirements
- Docker (recommended)
- Alternatively:
  - Protocol Buffer Compiler (protoc) version 3.19.1 exactly
  - CMake 3.10+
  - GCC 9.4+ with C++17 support
  - Python 3.7 or 3.8

## Diplomacy Cicero Build Process
See [DIPCC_BUILD_NOTES.md](./DIPCC_BUILD_NOTES.md) for detailed instructions on building the C++ components.

### Build Dependencies
1. **Protocol Buffers**: Used for configuration and serialization
   - Version 3.19.1 must be built from source to avoid compatibility issues
   - Required for parsing `.proto` files in the `conf/` directory
   
2. **dipcc**: C++ implementation of the Diplomacy game logic
   - Located in the `dipcc/` directory
   - Compiles to a shared library
   - Provides Python bindings via pybind11
   
3. **fairdiplomacy**: Python module that depends on dipcc
   - Imports dipcc as `fairdiplomacy.pydipcc`
   
4. **parlai_diplomacy**: Modified ParlAI framework for dialogue generation

### Build Order
The correct build sequence is:
1. Install system dependencies
2. Build protobuf 3.19.1 from source
3. Compile `.proto` files to Python modules
4. Compile dipcc C++ library and Python bindings
5. Install Python dependencies
6. Install the Python package

### Common Issues
- Protocol buffer syntax errors with protobuf versions other than 3.19.1
- Import errors between dipcc and fairdiplomacy.pydipcc
- C++ compilation failures due to GCC version incompatibility
- CUDA/GPU acceleration configuration issues

## Build & Testing Commands
- Compile and build: `make compile`
- Compile protobuf only: `make protos_basic`
- Compile dipcc only: `cd dipcc && ./compile.sh`
- Run all tests: `make test`
- Run fast tests: `make test_fast`
- Run single test: `python -m pytest path/to/test.py::test_function -v`
- Run tests with filter: `pytest -k pattern`
- Run tests with output: `pytest -s`
- Show test durations: `pytest --durations=0`
- Check types: `./bin/pyright_local.py`

## Code Style Guidelines
- **Python**: 3.7+ with static typing
- **C++**: C++17 with pybind11 for Python bindings
- **Formatting**: Use black with line length of 99 (`black . --line-length=99`)
- **Imports**: Standard first, third-party next, project imports last, separated by blank lines
- **Naming**: snake_case for variables/functions, PascalCase for classes
- **Error handling**: Use explicit exception handling with descriptive messages
- **Pre-commit**: Run `pre-commit install` to auto-format code before commits
- **Protobuf**: Format with `clang-format-8 conf/*.proto -i`
- **Documentation**: Use docstrings for functions and methods, especially for public APIs
- **Testing**: Write pytest tests with descriptive names in unit_tests/ directory

## Next Steps for Docker and Build Improvements

1. **Test Cross-Platform Compatibility**:
   - Test the build on both x86_64 and ARM64 architectures
   - Modify module loading to dynamically detect platform-specific `.so` files
   - Add platform-specific build options and documentation

2. **Optimize Memory Usage**:
   - Experiment with Docker build memory limits and compilation flags
   - Create a multi-stage build to reduce final image size
   - Add resource requirement documentation for different build configurations

3. **Strengthen Protobuf Handling**:
   - Create validation tests for protobuf compilation correctness
   - Document protobuf version requirements more prominently
   - Add better error handling for protobuf version mismatches

4. **Improve Validation**:
   - Expand test_pydipcc.py to validate more functionality
   - Add tests for model loading and game state manipulation
   - Create specific tests for Python-C++ integration points

5. **Document Integration Points**:
   - Document the relationship between dipcc and fairdiplomacy.pydipcc more clearly
   - Create a visual diagram of module dependencies
   - Add examples of correct import paths and usage

6. **Refine Docker Workflow**:
   - Consolidate the regular and phased Dockerfiles
   - Add CI pipeline instructions for automated building and testing
   - Create Docker Compose profiles for different use cases

7. **Create Release Process**:
   - Document how to create versioned Docker images
   - Add tagging conventions for built images
   - Test integration with model weight downloading

8. **Deployment Instructions**:
   - Add detailed instructions for deploying in production environments
   - Document resource requirements (memory, CPU, GPU)
   - Include performance optimization guidelines