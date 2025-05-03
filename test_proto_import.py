
import sys
import os

# Add the current directory to the path so we can import the conf modules
sys.path.insert(0, os.getcwd())

try:
    from conf import conf_pb2
    print("Successfully imported conf_pb2")
    
    # Try to create a config object
    config = conf_pb2.Config()
    print("Successfully created a Config object")
    
    # Try other imports
    from conf import agents_pb2, common_pb2, misc_pb2
    print("Successfully imported all protobuf modules")
    
    print("PROTOBUF FIXES SUCCESSFUL!")
except Exception as e:
    print(f"Error importing protobuf modules: {e}")
    sys.exit(1)
