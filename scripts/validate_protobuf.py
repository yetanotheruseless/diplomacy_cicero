#!/usr/bin/env python3
"""
Validation script for testing protobuf compilation and version compatibility.

This script:
1. Verifies the installed protobuf version
2. Tests loading all compiled protobuf modules
3. Creates a simple test message to verify serialization
4. Validates required protobuf features are working
"""

import os
import sys
import glob
import importlib
import subprocess
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def configure_import_path() -> None:
    """Run validation relative to the repository root."""
    os.chdir(REPO_ROOT)
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f" {title} ".center(60, "-"))
    print("=" * 60)

def print_result(success, message):
    """Print a test result."""
    status = "PASS" if success else "FAIL"
    print(f"[{status}] {message}")
    return success

def check_protobuf_version():
    """Verify the installed protobuf version is 3.19.1."""
    print_section("PROTOBUF VERSION CHECK")
    
    # Check Python protobuf version
    try:
        import google.protobuf
        pyversion = google.protobuf.__version__
        py_success = pyversion == "3.19.1"
        print_result(py_success, f"Python protobuf version: {pyversion} (expecting 3.19.1)")
    except ImportError:
        traceback.print_exc()
        py_success = False
        print_result(False, "Failed to import Python protobuf")
    
    # Check protoc version
    try:
        result = subprocess.run(["protoc", "--version"], 
                               capture_output=True, text=True, check=True)
        protoc_version = result.stdout.strip()
        protoc_success = "3.19.1" in protoc_version
        print_result(protoc_success, f"protoc version: {protoc_version} (expecting 3.19.1)")
    except (subprocess.SubprocessError, FileNotFoundError):
        traceback.print_exc()
        protoc_success = False
        print_result(False, "Failed to check protoc version")
    
    return py_success and protoc_success

def find_proto_modules():
    """Find all compiled protobuf modules."""
    print_section("FIND PROTOBUF MODULES")
    
    # Expected modules
    expected_modules = [
        "conf/conf_pb2",
        "conf/agents_pb2",
        "conf/common_pb2",
        "conf/misc_pb2"
    ]
    
    # Find all *_pb2.py files
    pb2_files = glob.glob("conf/*_pb2.py")
    found_modules = [os.path.splitext(f)[0] for f in pb2_files]
    
    print(f"Found {len(found_modules)} protobuf modules:")
    for module in found_modules:
        print(f"  - {module}")
    
    # Check if all expected modules were found
    all_expected_found = all(module in found_modules for module in expected_modules)
    print_result(all_expected_found, "All expected protobuf modules found")
    
    return found_modules, all_expected_found

def import_proto_modules(modules):
    """Try to import all protobuf modules."""
    print_section("IMPORT PROTOBUF MODULES")
    
    import_results = []
    for module_path in modules:
        module_name = module_path.replace("/", ".")
        try:
            importlib.import_module(module_name)
            import_results.append((module_name, True))
            print_result(True, f"Successfully imported {module_name}")
        except Exception as e:
            import_results.append((module_name, False))
            print_result(False, f"Failed to import {module_name}: {e}")
            traceback.print_exc()
    
    all_imports_ok = all(result for _, result in import_results)
    return all_imports_ok

def test_minimal_protobuf():
    """Test creating a minimal protobuf message."""
    print_section("TEST MINIMAL PROTOBUF")

    try:
        try:
            import minimal_pb2
            print_result(True, "Imported minimal_pb2")
        except ImportError:
            if not os.path.exists("minimal.proto"):
                raise FileNotFoundError("minimal.proto is missing")
            print("minimal.proto exists but minimal_pb2.py was not found; compiling it")
            subprocess.run(["protoc", "minimal.proto", "--python_out=./"], check=True)
            importlib.invalidate_caches()
            import minimal_pb2
            print_result(True, "Compiled and imported minimal_pb2")

        # Create a test message
        message = minimal_pb2.TestMessage()
        message.text = "Test message for protobuf validation"
        message.number = 42

        # Serialize and deserialize
        serialized = message.SerializeToString()
        deserialized = minimal_pb2.TestMessage()
        deserialized.ParseFromString(serialized)

        # Check if the round trip worked
        round_trip_ok = (
            deserialized.text == message.text and deserialized.number == message.number
        )

        print_result(round_trip_ok, "Serialization and deserialization successful")
        print(f"Original message: text='{message.text}', number={message.number}")
        print(f"Deserialized message: text='{deserialized.text}', number={deserialized.number}")

        return round_trip_ok

    except Exception as e:
        print_result(False, f"Error in minimal protobuf test: {e}")
        traceback.print_exc()
        return False

def test_project_specific_proto():
    """Test loading a specific project protobuf message."""
    print_section("TEST PROJECT PROTOCOL BUFFERS")

    try:
        import conf.agents_pb2 as agents_pb2

        # Exercise the real Agent oneof rather than assigning a synthetic field.
        agent = agents_pb2.Agent()
        agent.random.SetInParent()
        print_result(True, "Successfully created Agent(random=RandomAgent())")

        serialized = agent.SerializeToString()
        deserialized = agents_pb2.Agent()
        deserialized.ParseFromString(serialized)

        round_trip_ok = deserialized.WhichOneof("agent") == "random"
        print_result(round_trip_ok, "Project-specific proto serialization successful")

        # Check if we can access other top-level messages
        if hasattr(agents_pb2, "DESCRIPTOR"):
            message_types = agents_pb2.DESCRIPTOR.message_types_by_name
            print(f"Available message types in agents.proto: {list(message_types.keys())}")

        return round_trip_ok

    except Exception as e:
        print_result(False, f"Error in project-specific protobuf test: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all validation tests."""
    configure_import_path()
    results = {}
    
    # Run all tests
    results["version_check"] = check_protobuf_version()
    modules, results["modules_found"] = find_proto_modules()
    results["imports_ok"] = import_proto_modules(modules)
    results["minimal_test"] = test_minimal_protobuf()
    results["project_test"] = test_project_specific_proto()
    
    # Print summary
    print_section("SUMMARY")
    all_passed = all(results.values())
    
    for test, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"{test.ljust(20)}: {status}")
    
    if all_passed:
        print("\n✅ All protobuf validation tests passed!")
        return 0
    else:
        print("\n❌ Some protobuf validation tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
