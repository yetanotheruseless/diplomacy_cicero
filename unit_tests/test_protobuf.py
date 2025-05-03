#!/usr/bin/env python
"""
Simple test for protobuf functionality.
"""
import unittest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from conf import conf_pb2, common_pb2, agents_pb2

class ProtobufTest(unittest.TestCase):
    """Test protobuf functionality"""
    
    def test_power_enum(self):
        """Test that power enum works correctly"""
        # Test that we can access the Power enum values
        self.assertEqual(common_pb2.Power.FRANCE, 2)
        self.assertEqual(common_pb2.Power.ENGLAND, 1)
        self.assertEqual(common_pb2.Power.GERMANY, 3)

    def test_include_message(self):
        """Test that we can create an Include message"""
        # Create an Include message and set its fields
        include = common_pb2.Include()
        include.path = "test_path"
        self.assertEqual(include.path, "test_path")

if __name__ == "__main__":
    unittest.main()