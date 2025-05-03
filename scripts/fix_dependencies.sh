#!/bin/bash
# Script to fix missing dependencies for the build process

# Check if virtual environment is active
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Please activate the virtual environment first with:"
    echo "  source .venv/bin/activate"
    exit 1
fi

# Install required Python packages
echo "Installing required Python packages..."
pip install protobuf pybind11

# Check for pybind11-config for CMake
if ! command -v pybind11-config &> /dev/null; then
    echo "Installing pybind11 for CMake..."
    if [ "$(uname)" == "Darwin" ]; then
        # macOS
        brew install pybind11
    elif [ "$(uname)" == "Linux" ]; then
        # Ubuntu/Debian
        if command -v apt-get &> /dev/null; then
            sudo apt-get install -y python3-pybind11
        else
            echo "Please install pybind11 development files manually."
        fi
    fi
fi

echo "Dependencies installed. Try running 'make compile' again."