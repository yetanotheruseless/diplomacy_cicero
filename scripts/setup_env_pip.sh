#!/bin/bash
# Setup script for Diplomacy Cicero using standard pip

# Check if python is installed
if ! command -v python &> /dev/null; then
    echo "Python is not installed. Please install Python first."
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

# Create a virtual environment
echo "Creating virtual environment..."
python -m venv .venv

# Activate the virtual environment
echo "Activating virtual environment..."
. .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -e .

# Run post-install hooks to compile protobuf schemas
echo "Running post-install hooks..."
python setup_hooks.py

# Install the pre-commit hooks if pre-commit is available
if command -v pre-commit &> /dev/null; then
    echo "Installing pre-commit hooks..."
    pre-commit install
else
    echo "pre-commit not available, skipping hook installation"
    echo "To install pre-commit hooks later, run: pre-commit install"
fi

echo "Environment setup complete!"
echo "To activate the environment, run:"
echo "  source .venv/bin/activate"