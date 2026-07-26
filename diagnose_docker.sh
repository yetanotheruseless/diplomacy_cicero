#!/bin/bash
# Script to diagnose and fix pydipcc inside the Docker container

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
cat > fix_dipcc.sh << EOF
#!/bin/bash
cd /app

echo "=== FINDING PYDIPCC MODULES ==="
find . -name "pydipcc*.so"

echo -e "\n=== CHECKING FAIRDIPLOMACY/__INIT__.PY ==="
cat fairdiplomacy/__init__.py

echo -e "\n=== ATTEMPTING TO IMPORT PYDIPCC WITH DIAGNOSTICS ==="
python -c "import sys; from fairdiplomacy import pydipcc; print('Module path:', getattr(pydipcc, '__file__', 'No file attribute')); print('Module contents:', dir(pydipcc)); print('Game exists:', hasattr(pydipcc, 'Game')); print('sys.modules keys:', [k for k in sys.modules.keys() if 'dipcc' in k or 'pydipcc' in k])" || echo "Import failed"

echo -e "\n=== TESTING GAME IMPORT ==="
python -c "from fairdiplomacy.pydipcc import Game; print('Game imported successfully!')" || echo "Game import failed"

echo -e "\n=== MODIFYING FAIRDIPLOMACY/__INIT__.PY ==="
cp fairdiplomacy/__init__.py fairdiplomacy/__init__.py.bak
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
            sys.modules["fairdiplomacy.pydipcc"] = pydipcc
            sys.modules["pydipcc"] = pydipcc  # Also make it available directly
            sys.modules["dipcc"] = pydipcc    # Make it available as dipcc too
            return pydipcc
    
    raise ImportError(f"Could not find pydipcc module. Looked in: {current_dir}")

# Load the module
pydipcc = load_pydipcc()

# Add a print for our diagnostics
print("pydipcc loaded, Game exists:", hasattr(pydipcc, 'Game'))
EOL

echo -e "\n=== TESTING WITH MODIFIED __INIT__.PY ==="
python -c "from fairdiplomacy.pydipcc import Game; print('Game imported successfully!')" || echo "Game import still failed"

echo -e "\n=== TESTING DIPCC IMPORT ==="
python -c "import dipcc; print('dipcc imported successfully!'); print('Game exists:', hasattr(dipcc, 'Game'))" || echo "dipcc import failed"

echo -e "\n=== TESTING RUN.PY HELP ==="
python run.py --help || echo "run.py --help failed"

echo -e "\n=== DONE ==="
EOF

chmod +x fix_dipcc.sh

# Run the script inside the Docker container
print_header "RUNNING DIAGNOSTICS IN DOCKER CONTAINER"
docker-compose run --rm diplomacy bash -c "cd /app && bash -e /app/fix_dipcc.sh"

# Clean up
rm fix_dipcc.sh
print_header "DIAGNOSTICS COMPLETE"