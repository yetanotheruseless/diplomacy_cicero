#!/bin/bash
# Script to set up Diplomacy Cicero with conda

# Check if conda is installed
if ! command -v conda &> /dev/null; then
    echo "conda is not installed. Please install conda first."
    echo "Visit https://docs.conda.io/en/latest/miniconda.html for installation instructions."
    exit 1
fi

# Check if protoc is installed
if ! command -v protoc &> /dev/null; then
    echo "Warning: protoc (Protocol Buffer Compiler) is not installed."
    echo "You'll need to install it for the project to work correctly."
    echo "On macOS: brew install protobuf"
    echo "On Ubuntu: apt-get install protobuf-compiler"
    echo "Continue anyway? (y/N)"
    read -r response
    if [[ "$response" != "y" && "$response" != "Y" ]]; then
        exit 1
    fi
fi

# Check if cmake is installed
if ! command -v cmake &> /dev/null; then
    echo "Warning: cmake is not installed."
    echo "You'll need to install it for compiling C++ components."
    echo "On macOS: brew install cmake"
    echo "On Ubuntu: apt-get install cmake"
    echo "Continue anyway? (y/N)"
    read -r response
    if [[ "$response" != "y" && "$response" != "Y" ]]; then
        exit 1
    fi
fi

# Create conda environment
echo "Creating conda environment..."
conda create --yes -n diplomacy_cicero python=3.7
echo "Activating conda environment..."
eval "$(conda shell.bash hook)"
conda activate diplomacy_cicero

# Install required conda packages
echo "Installing required conda packages..."
conda install --yes pybind11
conda install --yes protobuf=3.19.1

# Check if system is macOS
if [[ "$(uname)" == "Darwin" ]]; then
    echo "Detected macOS system..."
    # Install PyTorch without CUDA for Mac
    conda install --yes pytorch torchvision -c pytorch
else
    # Install PyTorch with CUDA for Linux
    conda install --yes pytorch=1.7.1 torchvision cudatoolkit=11.0 -c pytorch
fi

# Install Python requirements
echo "Installing Python requirements..."
# Use specific versions to avoid conflicts
pip install wheel setuptools
pip install cython numpy

# Try installing from requirements but exclude fairseq and torch-related packages
grep -v "fairseq\|torch" requirements.txt > modified_requirements.txt
pip install -r modified_requirements.txt

# Compile protobuf schemas
echo "Compiling protobuf schemas..."
protoc conf/*.proto --python_out ./

# Try building C++ components
echo "Building C++ components..."
make protos_basic

echo "Conda environment setup complete!"
echo "To activate the environment, run:"
echo "  conda activate diplomacy_cicero"