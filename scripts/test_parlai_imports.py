#!/usr/bin/env python
"""
Script to test that ParlAI modules can be imported.
"""
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    """Test importing various ParlAI modules"""
    try:
        print("Importing ParlAI modules...")
        import parlai
        print(f"✅ Successfully imported parlai {parlai.__version__}")
        
        import parlai_diplomacy
        print("✅ Successfully imported parlai_diplomacy")
        
        from parlai_diplomacy.utils import special_tokens
        print("✅ Successfully imported special_tokens")
        
    except ImportError as e:
        print(f"❌ Error importing ParlAI modules: {e}")
        sys.exit(1)
    
    print("All ParlAI imports successful!")
    sys.exit(0)

if __name__ == "__main__":
    main()