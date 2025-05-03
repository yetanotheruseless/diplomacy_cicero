#!/usr/bin/env python3
"""
Simple test script to verify the pydipcc module is built and working correctly.
"""
import os
import sys

# Try to import the module
try:
    # First try normal import
    from fairdiplomacy import pydipcc
    print("[SUCCESS] Successfully imported pydipcc module directly")
except ImportError:
    print("[INFO] Could not import pydipcc directly, checking for .so file...")
    
    # Look for the .so file
    import glob
    so_files = glob.glob("fairdiplomacy/pydipcc*.so")
    if so_files:
        print(f"[INFO] Found pydipcc .so file(s): {so_files}")
        
        # Try manual import
        import importlib.util
        spec = importlib.util.spec_from_file_location("pydipcc", so_files[0])
        if spec:
            pydipcc = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pydipcc)
            sys.modules["fairdiplomacy.pydipcc"] = pydipcc
            print("[SUCCESS] Successfully loaded pydipcc module from .so file")
        else:
            print("[ERROR] Failed to create module spec from .so file")
            sys.exit(1)
    else:
        print("[ERROR] No pydipcc .so files found in fairdiplomacy/ directory")
        sys.exit(1)

# Try to create a Game object
try:
    game = pydipcc.Game()
    print("[SUCCESS] Successfully created a Game object")
    print(f"Game state: {game.get_state()}")
    print(f"Current phase: {game.current_short_phase}")
    
    # Try a simple game operation
    print("\nGetting valid orders for Turkey:")
    valid_orders = game.get_all_possible_orders()
    for power, orders in valid_orders.items():
        if power == "TURKEY":
            print(f"TURKEY has {len(orders)} possible orders")
            for i, order in enumerate(orders[:5]):
                print(f"  {i+1}. {order}")
            if len(orders) > 5:
                print(f"  ... and {len(orders)-5} more")
    
    print("\n[SUCCESS] All tests passed! The pydipcc module is working correctly.")
except Exception as e:
    print(f"[ERROR] Failed to create or use Game object: {e}")
    sys.exit(1)