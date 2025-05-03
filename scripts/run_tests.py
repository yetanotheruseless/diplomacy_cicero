#!/usr/bin/env python
"""
Script to run unittest discovery on the diplomacy-cicero repository.
This will find and run all tests in the unit_tests directory.
"""
import os
import sys
import unittest

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    print("Running unit tests discovery...")
    
    # Find all tests in the unit_tests directory
    test_suite = unittest.defaultTestLoader.discover(
        'unit_tests',
        pattern='test_*.py',
        top_level_dir=os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    )
    
    # Run the tests
    test_runner = unittest.TextTestRunner(verbosity=2)
    result = test_runner.run(test_suite)
    
    # Return non-zero exit code if tests failed
    if not result.wasSuccessful():
        print(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
        sys.exit(1)
    else:
        print("All tests passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()