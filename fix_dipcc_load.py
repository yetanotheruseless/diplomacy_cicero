#!/usr/bin/env python3
"""
Script to fix dipcc loading by creating the right package structure.
"""
import os
import sys
import glob
import shutil
import importlib.util

def main():
    """Main function to fix dipcc loading."""
    print("Fixing dipcc loading...")
    
    # 1. Create proper directory structure
    print("Creating proper package structure...")
    os.makedirs("dipcc_pkg", exist_ok=True)
    
    # Create __init__.py in dipcc_pkg
    with open("dipcc_pkg/__init__.py", "w") as f:
        f.write("# Package initialization\n")
        f.write("from . import pydipcc\n")
        f.write("# Make the module available at the package level\n")
        f.write("Game = pydipcc.Game if hasattr(pydipcc, 'Game') else None\n")
    
    # Find the pydipcc.so file
    so_files = glob.glob("dipcc/build/dipcc/python/pydipcc*.so")
    if not so_files:
        print("Error: Could not find pydipcc.so file")
        return False
    
    # Copy the .so file to dipcc_pkg with the correct name
    so_source = so_files[0]
    so_target = "dipcc_pkg/pydipcc.so"
    print(f"Copying {so_source} to {so_target}...")
    shutil.copy2(so_source, so_target)
    
    # 2. Update sys.path to include our new package
    package_path = os.path.abspath("dipcc_pkg")
    print(f"Adding {package_path} to sys.path...")
    sys.path.insert(0, os.path.dirname(package_path))
    
    # 3. Try to import and use the module
    print("\nTrying to import the fixed module...")
    try:
        import dipcc_pkg
        print("Successfully imported dipcc_pkg")
        print(f"Available in dipcc_pkg: {dir(dipcc_pkg)}")
        
        if hasattr(dipcc_pkg, "Game"):
            print("Creating Game object...")
            game = dipcc_pkg.Game()
            print(f"Game created with ID: {game.game_id}")
            print(f"Current phase: {game.get_current_phase()}")
            return True
        else:
            print("Game class not found in dipcc_pkg")
            
            # Try direct import of pydipcc
            print("Trying direct import of pydipcc submodule...")
            from dipcc_pkg import pydipcc
            print(f"Available in pydipcc: {dir(pydipcc)}")
            
            if hasattr(pydipcc, "Game"):
                print("Creating Game object from pydipcc...")
                game = pydipcc.Game()
                print(f"Game created with ID: {game.game_id}")
                print(f"Current phase: {game.get_current_phase()}")
                return True
            else:
                print("Game class not found in dipcc_pkg.pydipcc")
                return False
    except Exception as e:
        print(f"Error importing/using dipcc_pkg: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    print(f"\nOverall result: {'SUCCESS' if success else 'FAILURE'}")