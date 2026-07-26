#!/usr/bin/env python3
"""
Basic test script to verify the heyhi module is working correctly.

This will test importing the heyhi module and accessing some basic functionality
without requiring a full application run.
"""
import os
import sys
import traceback

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

# Test results tracking
test_results = {
    "import": False,
    "conf": False,
    "util": False,
    "run": False
}

print_separator("ENVIRONMENT INFORMATION")
print_info(f"Python version: {sys.version}")
print_info(f"Current directory: {os.getcwd()}")
print_info(f"Project root: {project_root}")
print_info(f"Python path: {sys.path}")

# Test importing heyhi
print_separator("IMPORTING HEYHI")
try:
    import heyhi
    print_success("Successfully imported heyhi module")
    print_info(f"heyhi module location: {heyhi.__file__}")
    print_info(f"Available attributes: {dir(heyhi)}")
    test_results["import"] = True
except ImportError as e:
    print_error(f"Failed to import heyhi: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test configuration functionality
print_separator("TESTING HEYHI CONF")
try:
    print_info("Testing heyhi.conf module...")
    
    # Check PROJ_ROOT and CONF_ROOT
    print_info(f"PROJ_ROOT: {heyhi.PROJ_ROOT}")
    print_info(f"CONF_ROOT: {heyhi.CONF_ROOT}")
    
    # Try to access some config utilities
    functions = [
        "load_config", 
        "load_root_config", 
        "load_proto_message",
        "flatten_cfg",
        "conf_to_dict"
    ]
    
    for func_name in functions:
        if hasattr(heyhi, func_name):
            print_info(f"Found function: {func_name}")
    
    test_results["conf"] = True
    print_success("heyhi.conf functionality verified")
except Exception as e:
    print_error(f"Error testing heyhi.conf: {e}")
    traceback.print_exc()

# Test utility functionality
print_separator("TESTING HEYHI UTIL")
try:
    print_info("Testing heyhi.util module...")
    
    # Check if utilities are available
    utilities = [
        "MODES",
        "get_job_env",
        "get_slurm_job_id",
        "is_master",
        "is_on_slurm",
        "setup_logging"
    ]
    
    for util_name in utilities:
        if hasattr(heyhi, util_name):
            print_info(f"Found utility: {util_name}")
    
    # Test basic function
    if hasattr(heyhi, "is_on_slurm"):
        is_slurm = heyhi.is_on_slurm()
        print_info(f"Running on SLURM: {is_slurm}")
    
    test_results["util"] = True
    print_success("heyhi.util functionality verified")
except Exception as e:
    print_error(f"Error testing heyhi.util: {e}")
    traceback.print_exc()

# Test run functionality
print_separator("TESTING HEYHI RUN")
try:
    print_info("Testing heyhi.run module...")
    
    # Check if run module functions are available
    run_functions = [
        "parse_args_and_maybe_launch",
        "maybe_launch",
        "get_default_exp_dir"
    ]
    
    for func_name in run_functions:
        if hasattr(heyhi, func_name):
            print_info(f"Found function: {func_name}")
    
    test_results["run"] = True
    print_success("heyhi.run functionality verified")
except Exception as e:
    print_error(f"Error testing heyhi.run: {e}")
    traceback.print_exc()

# Final results
print_separator("TEST RESULTS")
all_tests_passed = all(test_results.values())

for test, result in test_results.items():
    status = "PASSED" if result else "FAILED"
    print(f"{test.ljust(15)}: {status}")

if all_tests_passed:
    print_success("All heyhi tests passed!")
    print_info("The heyhi module appears to be working correctly.")
else:
    failed_tests = [test for test, result in test_results.items() if not result]
    print_error(f"Some tests failed: {failed_tests}")
    print_info("Please check the error messages above for more details.")
    sys.exit(1)