#!/bin/bash
# Script to install minimal dependencies needed for running basic Diplomacy Cicero game functionality

echo "Installing minimal dependencies for Diplomacy Cicero..."

# Install pydipcc dependencies
pip install pybind11 numpy cython

# Install ParlAI from GitHub with the specific commit
echo "Installing ParlAI from GitHub (specific commit)..."
pip install git+https://github.com/facebookresearch/ParlAI.git@5214f42a2058ef335f91f5afe66b2bd9ebfb2fbe

# Install common dependencies
pip install attrs==20.2.0 joblib==1.1.0 tqdm==4.62.1 termcolor==1.1.0

echo "Minimal dependencies installed!"