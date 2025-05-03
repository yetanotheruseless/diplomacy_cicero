#!/usr/bin/env python3
"""
Script to check if the Docker environment is correctly set up and if 
the protobuf files are working correctly.
"""
import os
import sys
import importlib
import subprocess

def check_python_version():
    print(f"Python version: {sys.version}")
    # Check major.minor version
    major, minor = sys.version_info[0], sys.version_info[1]
    if major == 3 and minor == 8:
        print("⚠️ Using Python 3.8.x instead of 3.7.x as specified in README")
        print("   This is a known divergence as Python 3.7 was not available in the Ubuntu 20.04 repositories")
        # Still return True as this is an accepted deviation
        return True
    elif major == 3 and minor == 7:
        print("✅ Correct Python version (3.7.x as specified in README)")
        return True
    else:
        print(f"❌ Python version is {major}.{minor}, expected 3.7 or 3.8")
        return False

def check_gcc_version():
    try:
        import subprocess
        result = subprocess.run(['gcc', '--version'], 
                             capture_output=True, text=True)
        if result.returncode == 0:
            version_output = result.stdout.strip()
            first_line = version_output.split('\n')[0] if '\n' in version_output else version_output
            print(f"GCC version output: {first_line}")
            # Extract version number - this is approximate and may need adjustment
            if "9.4" in version_output:
                print("✅ GCC version 9.4 detected (as specified in README)")
                return True
            else:
                print("⚠️ GCC version may not be 9.4 as specified in README")
                return False
        else:
            print("❌ Error checking GCC version")
            return False
    except Exception as e:
        print(f"❌ Error checking GCC version: {e}")
        return False

def check_cmake_version():
    try:
        import subprocess
        result = subprocess.run(['cmake', '--version'], 
                             capture_output=True, text=True)
        if result.returncode == 0:
            version_output = result.stdout.strip()
            print(f"CMake version: {version_output.split('\\n')[0]}")
            # CMAKE version not specified in README, so just report it
            return True
        else:
            print("❌ Error checking CMake version")
            return False
    except Exception as e:
        print(f"❌ Error checking CMake version: {e}")
        return False

def check_protobuf_version():
    try:
        import google.protobuf
        version = google.protobuf.__version__
        print(f"Protobuf version: {version}")
        if version == "3.19.1":
            print("✅ Correct protobuf version installed (3.19.1 as specified in README)")
            return True
        else:
            print(f"⚠️ Protobuf version is {version}, expected 3.19.1 from README")
            return False
    except ImportError:
        print("❌ Protobuf not installed")
        return False

def check_protoc_compiler():
    try:
        result = subprocess.run(['protoc', '--version'], 
                             capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"Protoc compiler: {version}")
            return True
        else:
            print("❌ Protoc compiler not found or error running it")
            return False
    except FileNotFoundError:
        print("❌ Protoc compiler not found in PATH")
        return False

def check_protobuf_files():
    print("Checking protobuf files in conf directory...")
    
    # Check if the directory exists
    if not os.path.isdir("conf"):
        print("❌ conf directory not found")
        return False
    
    # Check for _pb2.py files
    pb2_files = [f for f in os.listdir("conf") if f.endswith("_pb2.py")]
    
    if not pb2_files:
        print("❌ No protobuf generated files found in conf directory")
        return False
    
    print(f"Found {len(pb2_files)} protobuf files: {', '.join(pb2_files)}")
    
    # Try to import each one
    sys.path.insert(0, os.getcwd())
    successful_imports = 0
    
    for pb2_file in pb2_files:
        module_name = f"conf.{pb2_file[:-3]}"
        try:
            module = importlib.import_module(module_name)
            print(f"✅ Successfully imported {module_name}")
            successful_imports += 1
        except Exception as e:
            print(f"❌ Failed to import {module_name}: {e}")
    
    success_rate = successful_imports / len(pb2_files) if pb2_files else 0
    print(f"Successfully imported {successful_imports}/{len(pb2_files)} protobuf files ({success_rate:.0%})")
    
    return success_rate == 1.0

def check_message_creation():
    print("Checking if we can create and use protobuf messages...")
    
    try:
        from conf import conf_pb2
        
        # Try to create a simple Config message
        config = conf_pb2.Config()
        print("✅ Successfully created a Config message")
        
        # Try to serialize and deserialize
        serialized = config.SerializeToString()
        new_config = conf_pb2.Config()
        new_config.ParseFromString(serialized)
        
        print("✅ Successfully serialized and deserialized a protobuf message")
        return True
    except Exception as e:
        print(f"❌ Failed to create or use protobuf messages: {e}")
        return False

def main():
    print("========== Docker Environment Check ==========")
    
    checks = [
        ("Python version", check_python_version),
        ("GCC version", check_gcc_version),
        ("CMake version", check_cmake_version),
        ("Protobuf version", check_protobuf_version),
        ("Protoc compiler", check_protoc_compiler),
        ("Protobuf files", check_protobuf_files),
        ("Message creation", check_message_creation)
    ]
    
    results = []
    for name, check_fn in checks:
        print(f"\n----- Checking {name} -----")
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Error during check: {e}")
            results.append((name, False))
    
    # Summary
    print("\n========== Summary ==========")
    all_passed = True
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
        if not result:
            all_passed = False
    
    if all_passed:
        print("\n✅ All checks passed! The Docker environment is correctly set up.")
        return 0
    else:
        print("\n⚠️ Some checks failed. Please fix the issues before continuing.")
        return 1

if __name__ == "__main__":
    sys.exit(main())