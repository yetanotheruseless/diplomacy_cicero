#!/usr/bin/env python3
"""
Script to test if protobuf is working correctly.
"""
import sys
import os

print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")

try:
    import google.protobuf
    print(f"Protobuf version: {google.protobuf.__version__}")
    print("✅ Protobuf import successful")
except ImportError as e:
    print(f"❌ Protobuf import failed: {e}")

try:
    # Create a simple test proto file
    with open('test_message.proto', 'w') as f:
        f.write('''
syntax = "proto3";

message TestMessage {
  string text = 1;
  int32 number = 2;
}
''')
    
    # Compile it
    import subprocess
    result = subprocess.run(['protoc', '--python_out=.', 'test_message.proto'], 
                          capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Protobuf compilation failed: {result.stderr}")
    else:
        print("✅ Protobuf compilation successful")
        print(f"Generated files: {', '.join(f for f in os.listdir('.') if f.endswith('_pb2.py'))}")
    
    # Try to import the generated file - make sure we're looking in the right place
    sys.path.insert(0, os.getcwd())
    
    # Check if file exists
    if os.path.exists('test_message_pb2.py'):
        print(f"✅ Found test_message_pb2.py: {os.path.getsize('test_message_pb2.py')} bytes")
    else:
        print("❌ test_message_pb2.py file not found")
        
    # Explicit import
    import importlib.util
    if os.path.exists('test_message_pb2.py'):
        spec = importlib.util.spec_from_file_location("test_message_pb2", "test_message_pb2.py")
        test_message_pb2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test_message_pb2)
        
        # Create a message
        message = test_message_pb2.TestMessage()
        message.text = "Hello from protobuf!"
        message.number = 42
        
        # Serialize and deserialize
        serialized = message.SerializeToString()
        new_message = test_message_pb2.TestMessage()
        new_message.ParseFromString(serialized)
        
        print(f"✅ Protobuf serialization works. Deserialized message: text='{new_message.text}', number={new_message.number}")
    
except Exception as e:
    print(f"❌ Protobuf test failed: {e}")
    import traceback
    traceback.print_exc()