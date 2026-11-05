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
