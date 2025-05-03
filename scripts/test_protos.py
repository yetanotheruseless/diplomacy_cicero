#!/usr/bin/env python
"""
Script to test that protobuf files load correctly.
"""
import os
import sys

# Add current directory to Python path
sys.path.insert(0, os.getcwd())

try:
    import conf.conf_pb2
    import conf.common_pb2
    import conf.misc_pb2
    import conf.agents_pb2
    print("Successfully imported all protobuf modules!")
    sys.exit(0)
except Exception as e:
    print(f"Error importing protobuf modules: {str(e)}", file=sys.stderr)
    sys.exit(1)