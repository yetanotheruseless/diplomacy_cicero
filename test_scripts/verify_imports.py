#!/usr/bin/env python3
"""
Test script to verify all the critical imports in the codebase.

This will attempt to import major modules in the correct order to identify
any import issues or missing dependencies.
"""
import os
import sys
import traceback
import time

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def print_separator(title):
    print("\n" + "=" * 60)
    print(f" {title} ".center(60, "-"))
    print("=" * 60)

def print_info(msg):
    print(f"[INFO] {msg}")

def print_success(msg):
    print(f"[SUCCESS] {msg}")

def print_error(msg):
    print(f"[ERROR] {msg}")

def print_warning(msg):
    print(f"[WARNING] {msg}")

def test_import(module_name, from_package=None):
    """Test importing a module and return success status."""
    start_time = time.time()
    try:
        if from_package:
            package = __import__(from_package, fromlist=[module_name])
            getattr(package, module_name)
            print_success(f"Successfully imported {from_package}.{module_name} in {time.time() - start_time:.2f}s")
        else:
            __import__(module_name)
            print_success(f"Successfully imported {module_name} in {time.time() - start_time:.2f}s")
        return True
    except ImportError as e:
        print_error(f"Failed to import {module_name}: {e}")
        return False
    except Exception as e:
        print_error(f"Error during import of {module_name}: {e}")
        traceback.print_exc()
        return False

# Basic modules that should be importable
basic_modules = [
    "os", "sys", "json", "numpy", "torch"
]

# Protocol buffer related modules
proto_modules = [
    "google.protobuf",
    "conf",
    "conf.conf_pb2",
    "conf.agents_pb2"
]

# Core project modules
core_modules = [
    "heyhi",
    "fairdiplomacy",
    "fairdiplomacy.pydipcc"  
]

# Advanced modules
advanced_modules = [
    ("agents", "fairdiplomacy"),
    ("models", "fairdiplomacy"),
    ("game", "fairdiplomacy"),
    ("typedefs", "fairdiplomacy")
]

# More advanced modules
very_advanced_modules = [
    "fairdiplomacy.agents.base_agent",
    "fairdiplomacy.models.base_strategy_model",
    "parlai_diplomacy"
]

print_separator("ENVIRONMENT INFORMATION")
print_info(f"Python version: {sys.version}")
print_info(f"Current directory: {os.getcwd()}")
print_info(f"Project root: {project_root}")
print_info(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")

# Test basic modules
print_separator("BASIC MODULES")
basic_results = {module: test_import(module) for module in basic_modules}

# Test protocol buffer modules
print_separator("PROTOCOL BUFFER MODULES")
proto_results = {module: test_import(module) for module in proto_modules}

# Test core modules
print_separator("CORE PROJECT MODULES")
core_results = {module: test_import(module) for module in core_modules}

# Test advanced modules
print_separator("ADVANCED MODULES")
advanced_results = {f"{pkg}.{mod}": test_import(mod, pkg) for mod, pkg in advanced_modules}

# Test very advanced modules
print_separator("VERY ADVANCED MODULES")
very_advanced_results = {module: test_import(module) for module in very_advanced_modules}

# Check pydipcc in more detail if it was imported successfully
if core_results.get("fairdiplomacy.pydipcc", False):
    print_separator("PYDIPCC DETAILS")
    try:
        from fairdiplomacy import pydipcc
        print_info(f"pydipcc module location: {getattr(pydipcc, '__file__', 'Unknown')}")
        print_info(f"Available in pydipcc: {dir(pydipcc)[:10]}...")
        
        # Try creating a game object
        try:
            game = pydipcc.Game()
            print_success("Successfully created a pydipcc.Game object")
            print_info(f"Game phase: {game.get_current_phase()}")
        except Exception as e:
            print_error(f"Failed to create Game object: {e}")
    except Exception as e:
        print_error(f"Error inspecting pydipcc: {e}")

# Final results summary
print_separator("IMPORT TEST RESULTS")

all_results = {}
all_results.update(basic_results)
all_results.update(proto_results)
all_results.update(core_results)
all_results.update(advanced_results)
all_results.update(very_advanced_results)

# Count passed and failed
passed = sum(1 for result in all_results.values() if result)
failed = sum(1 for result in all_results.values() if not result)

print_info(f"Total imports tested: {len(all_results)}")
print_info(f"Successful imports: {passed}")
print_info(f"Failed imports: {failed}")

# Print failed imports for easy reference
if failed > 0:
    print_separator("FAILED IMPORTS")
    for module, result in all_results.items():
        if not result:
            print_error(f"Failed to import: {module}")

# Conclusion
if failed == 0:
    print_separator("CONCLUSION")
    print_success("All imports succeeded!")
    sys.exit(0)
else:
    print_separator("CONCLUSION")
    print_error(f"{failed} imports failed. See above for details.")
    sys.exit(1)