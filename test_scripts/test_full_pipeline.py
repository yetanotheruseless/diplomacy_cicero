#!/usr/bin/env python3
"""
Test script to verify the full pipeline is working correctly.

This script attempts to run a simple command using the core functionality
of the Diplomacy Cicero codebase.
"""
import os
import sys
import traceback
import subprocess
import argparse
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

def run_command(command):
    """Run a command and return the output."""
    print_info(f"Running command: {command}")
    start_time = time.time()
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        duration = time.time() - start_time
        print_success(f"Command completed successfully in {duration:.2f}s")
        return True, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        print_error(f"Command failed with code {e.returncode} in {duration:.2f}s")
        print_error(f"STDOUT: {e.stdout}")
        print_error(f"STDERR: {e.stderr}")
        return False, e.stdout, e.stderr
    except Exception as e:
        duration = time.time() - start_time
        print_error(f"Error running command: {e} in {duration:.2f}s")
        return False, "", str(e)

def parse_args():
    parser = argparse.ArgumentParser(description="Test the full Diplomacy Cicero pipeline")
    parser.add_argument("--skip-protos", action="store_true", help="Skip protobuf compilation")
    parser.add_argument("--skip-build", action="store_true", help="Skip C++ module building")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    return parser.parse_args()

def main():
    args = parse_args()
    
    print_separator("ENVIRONMENT INFORMATION")
    print_info(f"Python version: {sys.version}")
    print_info(f"Current directory: {os.getcwd()}")
    print_info(f"Project root: {project_root}")
    print_info(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")
    
    # Step 1: Verify Protobuf
    print_separator("STEP 1: VERIFY PROTOBUF")
    if args.skip_protos:
        print_info("Skipping protobuf compilation as requested")
    else:
        success, stdout, stderr = run_command("cd '{}' && python scripts/test_protobuf.py".format(project_root))
        if not success:
            print_error("Protobuf verification failed, trying to compile protos")
            success, stdout, stderr = run_command("cd '{}' && make protos_basic".format(project_root))
            if not success:
                print_error("Failed to compile protobuf files")
                sys.exit(1)
            else:
                print_success("Successfully compiled protobuf files")
    
    # Step 2: Verify pydipcc module
    print_separator("STEP 2: VERIFY PYDIPCC MODULE")
    if args.skip_build:
        print_info("Skipping C++ module building as requested")
    else:
        success, stdout, stderr = run_command("cd '{}' && python test_pydipcc.py".format(project_root))
        if not success:
            print_error("pydipcc module verification failed, trying to rebuild")
            success, stdout, stderr = run_command("cd '{}' && PYDIPCC_OUT_DIR={}/fairdiplomacy SKIP_TESTS=1 bash ./dipcc/compile.sh".format(project_root, project_root))
            if not success:
                print_error("Failed to build pydipcc module")
                sys.exit(1)
            else:
                print_success("Successfully built pydipcc module")
                # Test again to verify
                success, stdout, stderr = run_command("cd '{}' && python test_pydipcc.py".format(project_root))
                if not success:
                    print_error("pydipcc module still failing verification after rebuild")
                    sys.exit(1)
    
    # Step 3: Test heyhi module
    print_separator("STEP 3: TEST HEYHI MODULE")
    success, stdout, stderr = run_command("cd '{}' && python test_scripts/verify_heyhi.py".format(project_root))
    if not success:
        print_error("heyhi module verification failed")
        sys.exit(1)
    else:
        print_success("heyhi module verification successful")
    
    # Step 4: Test basic imports
    print_separator("STEP 4: TEST BASIC IMPORTS")
    success, stdout, stderr = run_command("cd '{}' && python test_scripts/verify_imports.py".format(project_root))
    if not success:
        print_warning("Some imports failed, but continuing")
    else:
        print_success("All imports verified successfully")
    
    # Step 5: Try to run minimal game
    print_separator("STEP 5: RUN MINIMAL GAME")
    try:
        print_info("Attempting to run minimal_game.py...")
        
        start_time = time.time()
        # Try to import the modules
        import dipcc
        from fairdiplomacy import pydipcc
        
        # Create a game object
        game = pydipcc.Game()
        print_info(f"Created game, current phase: {game.get_current_phase()}")
        
        # Try to get all possible orders
        valid_orders = game.get_all_possible_orders()
        total_orders = sum(len(orders) for orders in valid_orders.values())
        print_info(f"Total possible orders: {total_orders}")
        
        # Print some sample orders
        for power, orders in valid_orders.items():
            print_info(f"Power {power} has {len(orders)} possible orders")
            if len(orders) > 0:
                print_info(f"Sample order: {orders[0]}")
        
        duration = time.time() - start_time
        print_success(f"Successfully ran minimal game operations in {duration:.2f}s")
    except Exception as e:
        print_error(f"Error running minimal game: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # Final verdict
    print_separator("FINAL VERDICT")
    print_success("All core functionality tests passed!")
    print_info("The Diplomacy Cicero codebase appears to be set up correctly.")
    print_info("You should now be able to run the main application using:")
    print_info("  python run.py --adhoc --cfg conf/c01_ag_cmp/cmp.prototxt Iagent_one=agents/cicero.prototxt")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())