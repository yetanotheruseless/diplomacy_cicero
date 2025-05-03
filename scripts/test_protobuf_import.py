#!/usr/bin/env python3
"""
Test script to check if protobuf imports now work correctly.
"""
import sys
import os

# Add current directory to the path
sys.path.insert(0, os.getcwd())

def test_protobuf_imports():
    print("Testing protobuf imports...")
    
    try:
        from conf import conf_pb2
        print("✅ Successfully imported conf_pb2")
        
        # Try to create a config object
        config = conf_pb2.Config()
        print("✅ Successfully created a Config object")
        
        # Try other imports
        from conf import agents_pb2, common_pb2, misc_pb2
        print("✅ Successfully imported all protobuf modules")
        
        print("✅ PROTOBUF TESTS SUCCESSFUL!")
        return True
    except Exception as e:
        print(f"❌ Error importing protobuf modules: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_protobuf_imports()
    sys.exit(0 if success else 1)