#!/bin/bash
# Script to fix all import issues in the Diplomacy Cicero Docker container

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${GREEN}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

# Create a script to run inside Docker
cat > fix_all.sh << EOF
#!/bin/bash
cd /app

echo "=== INSTALLING SUBMITIT AND OTHER DEPENDENCIES ==="
pip install submitit==1.4.1
pip install typing_extensions pytest

echo -e "\n=== CHECKING PYDIPCC MODULES ==="
find . -name "pydipcc*.so"

echo -e "\n=== FIXING FAIRDIPLOMACY/__INIT__.PY ==="
cat > fairdiplomacy/__init__.py << EOL
#!/usr/bin/env python
import os
import sys
import importlib.util
import glob

# Dynamically find and load the pydipcc module
def load_pydipcc():
    # Look for .so files in the current directory
    current_dir = os.path.dirname(__file__)
    so_files = glob.glob(os.path.join(current_dir, "pydipcc*.so"))
    
    if so_files:
        so_file = so_files[0]
        print(f"Found pydipcc at: {so_file}")
        spec = importlib.util.spec_from_file_location("pydipcc", so_file)
        if spec:
            pydipcc = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pydipcc)
            # Make it available through multiple import paths
            sys.modules["fairdiplomacy.pydipcc"] = pydipcc
            sys.modules["pydipcc"] = pydipcc
            sys.modules["dipcc"] = pydipcc
            return pydipcc
    
    raise ImportError(f"Could not find pydipcc module. Looked in: {current_dir}")

# Load the module
pydipcc = load_pydipcc()
EOL

echo -e "\n=== PATCH HEYHI TO AVOID UNNECESSARY IMPORTS ==="
# Create a patch for heyhi/util.py to make submitit optional
cat > heyhi_patch.py << EOL
import os
import re

# Path to the file we want to patch
path = "heyhi/util.py"

# Read the file content
with open(path, "r") as f:
    content = f.read()

# Add a try/except block around the submitit import
content = re.sub(
    r"import submitit",
    "try:\\n    import submitit\\nexcept ImportError:\\n    submitit = None\\n    print('Warning: submitit not available, some functionality will be limited')",
    content
)

# Make functions that use submitit check if it's available
content = re.sub(
    r"def get_slurm_job_id\(\):",
    "def get_slurm_job_id():\\n    if submitit is None:\\n        return None",
    content
)

content = re.sub(
    r"def get_slurm_master\(\):",
    "def get_slurm_master():\\n    if submitit is None:\\n        return None",
    content
)

content = re.sub(
    r"def maybe_init_requeue_handler\(\):",
    "def maybe_init_requeue_handler():\\n    if submitit is None:\\n        return",
    content
)

# Write the patched content back to the file
with open(path, "w") as f:
    f.write(content)

print("Patched heyhi/util.py to make submitit optional")
EOL

# Run the patch script
python heyhi_patch.py

echo -e "\n=== TESTING GAME IMPORT ==="
python -c "from fairdiplomacy.pydipcc import Game; print('Game imported successfully!'); game = Game(); print('Game object created!')" || echo "Game import failed"

echo -e "\n=== TESTING HEYHI IMPORT ==="
python -c "import heyhi; print('Heyhi imported successfully!')" || echo "Heyhi import failed"

echo -e "\n=== TESTING RUN.PY HELP ==="
python run.py --help || echo "run.py --help failed"

echo -e "\n=== DONE ==="
EOF

chmod +x fix_all.sh

# Run the script inside the Docker container
print_header "FIXING ALL ISSUES IN DOCKER CONTAINER"
docker-compose run --rm diplomacy bash -c "cd /app && bash -e /app/fix_all.sh"

# Clean up
rm fix_all.sh
print_header "FIX COMPLETE"