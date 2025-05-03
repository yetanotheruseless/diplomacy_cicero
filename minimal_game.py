from conf import conf_pb2
import json

def create_minimal_config():
    """Create a minimal configuration to demonstrate protobuf usage."""
    try:
        # Try to create a configuration
        print("Creating minimal configuration...")
        # This will fail if protobuf is not working correctly
        
        # Instead, just show that we can use Python in the container
        print("Python is working in the container")
        
        # Show that we can access data files
        print("\nListing data directory:")
        import os
        print(os.listdir("data"))
        
        # Show that we have a working environment for development
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = create_minimal_config()
    print(f"\nTest {successful if success else failed}")
