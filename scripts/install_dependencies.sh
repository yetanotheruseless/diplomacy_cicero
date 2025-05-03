#!/bin/bash
# Script to install system dependencies needed for diplomacy_cicero

# Check if running on macOS
if [ "$(uname)" == "Darwin" ]; then
    echo "Installing dependencies on macOS using Homebrew..."
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo "Homebrew not found. Please install it from https://brew.sh/"
        exit 1
    fi
    
    # Install dependencies
    brew install cmake protobuf
    
    # Check if python is available through brew
    if brew list python &> /dev/null; then
        echo "Installing mypy-protobuf..."
        pip install mypy-protobuf
    else
        echo "Python not found through Homebrew. Please install mypy-protobuf manually:"
        echo "  pip install mypy-protobuf"
    fi
    
elif [ "$(uname)" == "Linux" ]; then
    # Assuming Ubuntu/Debian
    echo "Installing dependencies on Linux..."
    
    # Check if we have sudo access
    if command -v sudo &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y cmake protobuf-compiler python3-pip
        pip install mypy-protobuf
    else
        echo "No sudo access. Please install these packages manually:"
        echo "  - cmake"
        echo "  - protobuf-compiler"
        echo "  - mypy-protobuf (via pip)"
    fi
else
    echo "Unsupported operating system. Please install the following dependencies manually:"
    echo "  - cmake"
    echo "  - protobuf compiler (protoc)"
    echo "  - mypy-protobuf (via pip)"
fi

echo "Done! If there were any errors, please install the missing dependencies manually."