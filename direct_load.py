#!/usr/bin/env python3
"""
Direct module loader for pydipcc.so to bypass regular import mechanisms.
"""
import os
import sys
import glob
import importlib.util
import traceback

def find_so_files():
    """Find all pydipcc .so files in the project."""
    so_files = []
    search_paths = [
        "fairdiplomacy",
        "dipcc/build/dipcc/python",
        "dipcc/build/out",
        "/app/fairdiplomacy",
        "/app/dipcc/build/dipcc/python",
        "/app/dipcc/build/out",
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            pattern = os.path.join(path, "pydipcc*.so")
            so_files.extend(glob.glob(pattern))
    
    return so_files

def load_module_from_so(so_path):
    """Load a Python module directly from an .so file."""
    print(f"Attempting to load module from: {so_path}")
    
    try:
        # Create a module spec from the .so file
        spec = importlib.util.spec_from_file_location("direct_pydipcc", so_path)
        if not spec:
            print(f"Failed to create module spec from {so_path}")
            return None
        
        # Create a module from the spec
        module = importlib.util.module_from_spec(spec)
        
        # Execute the module (loads its contents)
        spec.loader.exec_module(module)
        
        # Register the module in sys.modules
        sys.modules["direct_pydipcc"] = module
        
        return module
    except Exception as e:
        print(f"Error loading module from {so_path}: {e}")
        traceback.print_exc()
        return None

def try_create_game(module):
    """Try to create a Game object using the module."""
    try:
        if hasattr(module, "Game"):
            print(f"Game class found in module!")
            game = module.Game()
            print(f"Successfully created game with ID: {game.game_id}")
            print(f"Current phase: {game.get_current_phase()}")
            return True
        else:
            print(f"Game class not found in module. Available attributes: {dir(module)}")
            return False
    except Exception as e:
        print(f"Error creating Game: {e}")
        traceback.print_exc()
        return False

def main():
    """Main entry point."""
    # Find all .so files
    so_files = find_so_files()
    print(f"Found .so files: {so_files}")
    
    if not so_files:
        print("No .so files found - cannot load pydipcc module")
        return False
    
    # Try loading from each .so file until one works
    for so_path in so_files:
        module = load_module_from_so(so_path)
        if module:
            print(f"Successfully loaded module from {so_path}")
            print(f"Module attributes: {dir(module)}")
            
            # Try creating a game
            if try_create_game(module):
                print("Successfully created a game!")
                return True
    
    print("Failed to load a working pydipcc module from any .so file")
    return False

if __name__ == "__main__":
    success = main()
    print(f"\nOverall result: {'SUCCESS' if success else 'FAILURE'}")