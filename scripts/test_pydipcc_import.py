#!/usr/bin/env python
"""
Script to test that pydipcc modules can be imported.
"""
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    """Test importing pydipcc modules"""
    try:
        print("Trying to import dipcc module...")
        import dipcc
        print(f"✅ Successfully imported dipcc")
        
        print("Trying to import fairdiplomacy.pydipcc...")
        try:
            from fairdiplomacy import pydipcc
            print("✅ Successfully imported fairdiplomacy.pydipcc")
            
            # Try to use the Game class
            print("Testing Game class from fairdiplomacy.pydipcc...")
            try:
                from fairdiplomacy.pydipcc import Game
                print("✅ Successfully imported Game class")
                
                # Try to create a new game
                print("Trying to create a new Game instance...")
                game = Game()
                print("✅ Successfully created Game instance")
            except (ImportError, AttributeError) as e:
                print(f"❌ Error using Game class: {e}")
                
        except ImportError as e:
            print(f"❌ Error importing fairdiplomacy.pydipcc: {e}")
            sys.exit(1)
        
    except ImportError as e:
        print(f"❌ Error importing dipcc: {e}")
        sys.exit(1)
    
    print("All imports successful!")
    sys.exit(0)

if __name__ == "__main__":
    main()