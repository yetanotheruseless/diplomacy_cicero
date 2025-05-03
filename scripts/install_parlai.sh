#!/bin/bash
# Install ParlAI from GitHub with the specific commit

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "git is not installed. Please install git first."
    exit 1
fi

# Install ParlAI from GitHub
echo "Installing ParlAI from GitHub (specific commit)..."
pip install git+https://github.com/facebookresearch/ParlAI.git@5214f42a2058ef335f91f5afe66b2bd9ebfb2fbe

echo "ParlAI installation complete!"