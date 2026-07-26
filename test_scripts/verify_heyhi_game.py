#!/usr/bin/env python3
"""
Verification script to confirm heyhi module is working properly in the Diplomacy Cicero codebase.
This script specifically tests the ability to load configurations and use run.py functionality.
"""
import os
import sys
import traceback

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Set up colored output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def print_section(title):
    """Print a section header."""
    print(f"\n{GREEN}{'=' * 70}{RESET}")
    print(f"{GREEN}=== {title}{RESET}")
    print(f"{GREEN}{'=' * 70}{RESET}")

def print_success(msg):
    """Print a success message."""
    print(f"{GREEN}✅ {msg}{RESET}")

def print_error(msg):
    """Print an error message."""
    print(f"{RED}❌ {msg}{RESET}")

def print_warning(msg):
    """Print a warning message."""
    print(f"{YELLOW}⚠️ {msg}{RESET}")

# Start verification
print_section("HEYHI VERIFICATION - GAME CONFIGURATION")
print("This script verifies that heyhi can load game configurations and other core functionality.")

# Track test results
tests_passed = 0
tests_failed = 0

# Test 1: Import heyhi
print_section("TEST 1: IMPORT HEYHI")
try:
    import heyhi
    print_success("Successfully imported heyhi module")
    print(f"heyhi module location: {heyhi.__file__}")
    tests_passed += 1
except ImportError as e:
    print_error(f"Failed to import heyhi: {e}")
    traceback.print_exc()
    tests_failed += 1
    sys.exit(1)  # Critical failure, exit

# Test 2: Access heyhi constants and utilities
print_section("TEST 2: ACCESS HEYHI CONSTANTS")
try:
    print(f"PROJ_ROOT: {heyhi.PROJ_ROOT}")
    print(f"CONF_ROOT: {heyhi.CONF_ROOT}")
    assert os.path.exists(heyhi.PROJ_ROOT), "PROJ_ROOT does not exist"
    assert os.path.exists(heyhi.CONF_ROOT), "CONF_ROOT does not exist"
    print_success("Successfully accessed heyhi constants")
    tests_passed += 1
except Exception as e:
    print_error(f"Failed to access heyhi constants: {e}")
    traceback.print_exc()
    tests_failed += 1

# Test 3: Load a protobuf configuration
print_section("TEST 3: LOAD PROTOBUF CONFIGURATION")
try:
    # Try to load a configuration file
    config_path = os.path.join(heyhi.CONF_ROOT, "c01_ag_cmp/cmp.prototxt")
    if not os.path.exists(config_path):
        print_warning(f"Config file not found at: {config_path}")
        # Try to find any prototxt file
        import glob
        prototxt_files = glob.glob(os.path.join(heyhi.CONF_ROOT, "**/*.prototxt"), recursive=True)
        if prototxt_files:
            config_path = prototxt_files[0]
            print_warning(f"Using alternative config file: {config_path}")
        else:
            raise FileNotFoundError("No .prototxt files found in conf directory")
    
    print(f"Loading config from: {config_path}")
    cfg = heyhi.load_config(config_path)
    print_success("Successfully loaded configuration file")
    print(f"Config type: {type(cfg)}")
    print(f"Config contains: {dir(cfg)[:10]}...")
    tests_passed += 1
except Exception as e:
    print_error(f"Failed to load configuration: {e}")
    traceback.print_exc()
    tests_failed += 1

# Test 4: Test run module
print_section("TEST 4: RUN MODULE")
try:
    # Import the run module
    from run import TASKS
    print(f"Available tasks: {list(TASKS.keys())}")
    
    # Check if common tasks exist
    expected_tasks = ['compare_agents', 'compare_agent_population', 'train', 'exploit']
    missing_tasks = [task for task in expected_tasks if task not in TASKS]
    if missing_tasks:
        print_warning(f"Some expected tasks missing: {missing_tasks}")
    else:
        print_success("All expected tasks available")
    
    tests_passed += 1
except Exception as e:
    print_error(f"Failed to access run module: {e}")
    traceback.print_exc()
    tests_failed += 1

# Test 5: Simple game initialization (not running a full game)
print_section("TEST 5: SIMPLE GAME INITIALIZATION")
try:
    from fairdiplomacy import pydipcc
    
    print("Creating a new game object...")
    game = pydipcc.Game()
    print(f"Game phase: {game.get_current_phase()}")
    print(f"Game state: {game.get_state()}")
    
    print_success("Successfully created game object")
    tests_passed += 1
except Exception as e:
    print_error(f"Failed to initialize game: {e}")
    traceback.print_exc()
    tests_failed += 1

# Final results
print_section("TEST RESULTS")
print(f"Tests passed: {tests_passed}")
print(f"Tests failed: {tests_failed}")

if tests_failed == 0:
    print_success("ALL TESTS PASSED!")
    print("\nNext steps for full game:")
    print("""
    # To play one Cicero agent as Turkey against six full-press imitation agents
    python run.py --adhoc --cfg conf/c01_ag_cmp/cmp.prototxt \\
        Iagent_one=agents/cicero.prototxt \\
        Iagent_six=agents/ablations/cicero_imitation_only.prototxt \\
        power_one=TURKEY
    """)
    sys.exit(0)
else:
    print_error(f"SOME TESTS FAILED: {tests_failed} test(s) failed")
    sys.exit(1)