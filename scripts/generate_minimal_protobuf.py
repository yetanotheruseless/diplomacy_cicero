#!/usr/bin/env python3
"""
Script to generate a minimal protobuf file to verify that protobuf works correctly.
This will be used as a template for fixing the problematic conf protobuf files.
"""

import os
import sys
import subprocess

def generate_minimal_protobuf():
    """Create and compile a minimal protobuf file."""
    print("Generating minimal protobuf file...")
    
    # Create a minimal proto file
    with open('minimal.proto', 'w') as f:
        f.write('''
syntax = "proto3";

message TestMessage {
  string text = 1;
  int32 number = 2;
}
''')
    
    # Compile it
    print("Compiling minimal.proto...")
    try:
        result = subprocess.run(['protoc', '--python_out=.', 'minimal.proto'], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Protobuf compilation failed: {result.stderr}")
            return False
        else:
            print("✅ Protobuf compilation successful")
            return True
    except Exception as e:
        print(f"❌ Error during protobuf compilation: {e}")
        return False

def print_minimal_pb2_file():
    """Print the minimal_pb2.py file to use as a template."""
    if not os.path.exists('minimal_pb2.py'):
        print("❌ minimal_pb2.py not found")
        return
    
    with open('minimal_pb2.py', 'r') as f:
        content = f.read()
    
    print("=== minimal_pb2.py CONTENT ===")
    print(content)
    print("=============================")
    
    return content

def create_protobuf_template():
    """Create a template file for protobuf fixes."""
    if not os.path.exists('minimal_pb2.py'):
        print("❌ minimal_pb2.py not found")
        return
    
    with open('minimal_pb2.py', 'r') as f:
        content = f.read()
    
    # Save the template
    with open('protobuf_template.py', 'w') as f:
        f.write(content)
    
    print(f"✅ Created protobuf_template.py")

if __name__ == "__main__":
    if generate_minimal_protobuf():
        template_content = print_minimal_pb2_file()
        create_protobuf_template()