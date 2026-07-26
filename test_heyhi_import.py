#!/usr/bin/env python3

"""Test script to verify heyhi module can be imported properly."""

try:
    # First check for torch, since it's required by heyhi
    try:
        import torch
        print("torch is available")
    except ImportError:
        print("Warning: torch is not installed, which is required by heyhi.")
        print("This test will focus only on importing the basic heyhi module.")
    
    # Try to import just the basic heyhi module
    import heyhi
    print("Successfully imported heyhi module!")
    
    # Try importing specific submodules that may not need torch
    try:
        from heyhi import conf
        print("Successfully imported heyhi.conf!")
    except Exception as e:
        print(f"Error importing heyhi.conf: {e}")
    
    # See if we can import util (might fail due to torch dependency)
    try:
        from heyhi import util
        print("Successfully imported heyhi.util!")
    except Exception as e:
        print(f"Error importing heyhi.util: {e}")
        
    print("Basic import test completed.")
except Exception as e:
    print(f"Error importing heyhi: {e}")