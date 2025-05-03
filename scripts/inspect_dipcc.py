#!/usr/bin/env python
"""
Script to inspect the contents of the dipcc module.
"""
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    """Inspect the dipcc module"""
    try:
        import dipcc
        print(f"Contents of dipcc module:")
        for name in dir(dipcc):
            if not name.startswith('__'):
                print(f"  - {name}")
        
        print(f"\nType of dipcc: {type(dipcc)}")
        print(f"File location: {dipcc.__file__}")
        
    except ImportError as e:
        print(f"❌ Error importing dipcc: {e}")
        sys.exit(1)
    
    sys.exit(0)

if __name__ == "__main__":
    main()