#!/usr/bin/env python3
"""
Script to check module exports and try to load the pydipcc module.
"""
import os
import sys
import glob
import subprocess
import importlib

def main():
    """Main function to check module exports and try different approaches."""
    # First, check the fairdiplomacy/__init__.py file
    print("Checking fairdiplomacy/__init__.py...")
    if os.path.exists("fairdiplomacy/__init__.py"):
        with open("fairdiplomacy/__init__.py", "r") as f:
            print(f.read())
    
    # Check what .so files exist
    print("\nLooking for .so files...")
    so_files = glob.glob("fairdiplomacy/*.so") + glob.glob("dipcc/build/dipcc/python/*.so")
    for so_file in so_files:
        print(f"Found: {so_file}")
        # Use nm to check exported symbols if available
        try:
            print(f"Checking symbols in {so_file}:")
            result = subprocess.run(["nm", "-D", so_file], capture_output=True, text=True)
            if result.returncode == 0:
                # Look for PyInit_ symbols
                for line in result.stdout.split("\n"):
                    if "PyInit_" in line:
                        print(f"  Export symbol found: {line}")
            else:
                print(f"  Error running nm: {result.stderr}")
        except Exception as e:
            print(f"  Error checking symbols: {e}")
    
    # Try importing dipcc directly
    print("\nTrying to import dipcc directly...")
    try:
        import dipcc
        print(f"Successfully imported dipcc")
        print(f"dipcc.__file__: {dipcc.__file__}")
        print(f"Available in dipcc: {dir(dipcc)}")
        
        # Try to create a Game
        if hasattr(dipcc, "Game"):
            print("Creating Game object...")
            game = dipcc.Game()
            print(f"Game created with ID: {game.game_id}")
        else:
            print("Game class not found in dipcc module")
    except Exception as e:
        print(f"Error importing dipcc: {e}")
    
    # Try the original import method
    print("\nTrying original import method...")
    try:
        # Add dipcc/build to Python path
        build_dir = os.path.abspath("dipcc/build")
        if build_dir not in sys.path:
            sys.path.insert(0, build_dir)
            print(f"Added {build_dir} to Python path")
        
        # Try importing pydipcc
        import pydipcc
        print(f"Successfully imported pydipcc")
        print(f"pydipcc.__file__: {getattr(pydipcc, '__file__', 'Unknown')}")
        print(f"Available in pydipcc: {dir(pydipcc)}")
    except Exception as e:
        print(f"Error importing pydipcc: {e}")
    
    # Create a sample file to try importing with the correct name
    print("\nCreating a sample file to try with the correct module name...")
    so_name = next((s for s in so_files if "pydipcc" in s), None)
    if so_name:
        module_name = os.path.basename(so_name).split(".")[0]
        print(f"Module name from .so file: {module_name}")
        
        try:
            # Try importing with the exact module name
            spec = importlib.util.find_spec(module_name)
            if spec:
                print(f"Found spec for {module_name}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                print(f"Successfully loaded {module_name}")
                print(f"Available attributes: {dir(module)}")
            else:
                print(f"Could not find spec for {module_name}")
        except Exception as e:
            print(f"Error importing {module_name}: {e}")
    else:
        print("No .so files found to extract module name")

if __name__ == "__main__":
    main()