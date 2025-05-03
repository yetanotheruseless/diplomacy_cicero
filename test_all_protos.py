
import sys
try:
    from conf import conf_pb2, agents_pb2, common_pb2, misc_pb2
    print("All main protobuf modules imported successfully")
    # Test creating a simple message
    msg = conf_pb2.Config()
    print("Successfully created a protobuf message")
except Exception as e:
    print(f"Error importing protobuf modules: {e}")
    sys.exit(1)

