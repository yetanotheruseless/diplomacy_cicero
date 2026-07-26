#!/usr/bin/env python3
"""
Debug script to investigate why units aren't able to move in Diplomacy Cicero.
"""
import os
import sys
import json

try:
    from fairdiplomacy.pydipcc import Game
except ImportError:
    print("Error: pydipcc module not found. Make sure it's built and in the right location.")
    sys.exit(1)

def print_header(title):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def inspect_game_state(game):
    """Inspect the game state in detail."""
    print_header("GAME STATE")
    
    phase = game.get_current_phase()
    print(f"Current phase: {phase}")
    
    print("\nIs this a movement phase?", phase.endswith("M"))
    print("Is this a retreat phase?", phase.endswith("R"))
    print("Is this a build phase?", phase.endswith("A") or phase.endswith("W"))
    
    state = game.get_state()
    print("\nState keys:", list(state.keys()))
    print(f"Phase name from state: {state.get('name', 'Unknown')}")
    
    print("\nGetting all possible orders...")
    all_orders = game.get_all_possible_orders()
    
    if not all_orders:
        print("No orders available for any power!")
    else:
        total_orders = sum(len(orders) for orders in all_orders.values())
        print(f"Total possible orders: {total_orders}")
        
        for power, orders in all_orders.items():
            print(f"\n{power} has {len(orders)} possible orders:")
            if len(orders) > 0:
                for i, order in enumerate(orders[:5]):
                    print(f"  {i+1}. {order}")
                if len(orders) > 5:
                    print(f"  ... and {len(orders)-5} more")
            else:
                print("  (No orders available)")

def test_initial_movement():
    """Test if units can move in the initial state."""
    print_header("TESTING INITIAL MOVEMENT")
    
    game = Game()
    print(f"Created new game, phase: {game.get_current_phase()}")
    
    # Inspect initial state
    inspect_game_state(game)
    
    # Get state with units
    state = game.get_state()
    units = state.get('units', {})
    print("\nUnits in initial state:")
    for power, power_units in units.items():
        print(f"{power}: {power_units}")
    
    # Try to submit some orders for testing
    print("\nTrying to submit orders for TURKEY:")
    orders = [
        "F ANK - BLA",  # Fleet Ankara to Black Sea
        "A SMY - CON",  # Army Smyrna to Constantinople
        "A CON - BUL"   # Army Constantinople to Bulgaria
    ]
    
    # First, check if these orders are valid
    all_orders = game.get_all_possible_orders()
    turkey_orders = all_orders.get("TURKEY", [])
    
    for order in orders:
        if order in turkey_orders:
            print(f"  ✓ Order is valid: {order}")
        else:
            print(f"  ✗ Order is not valid: {order}")
            # Try to find similar orders
            similar = [o for o in turkey_orders if order.split(" - ")[0] in o]
            if similar:
                print(f"    Similar valid orders: {similar[:3]}")
                if len(similar) > 3:
                    print(f"    ... and {len(similar)-3} more")
    
    # Try to submit the orders anyway
    try:
        game.set_orders("TURKEY", orders)
        print("\nSuccessfully set orders for TURKEY")
    except Exception as e:
        print(f"\nError setting orders: {e}")
    
    # Process the game
    try:
        game.process()
        print("\nGame processed successfully")
    except Exception as e:
        print(f"\nError processing game: {e}")
    
    # Check new state
    new_state = game.get_state()
    new_units = new_state.get('units', {})
    new_phase = game.get_current_phase()
    
    print(f"\nNew phase: {new_phase}")
    print("\nUnits after processing:")
    for power, power_units in new_units.items():
        print(f"{power}: {power_units}")
    
    # Check if units moved
    turkey_units_before = set(units.get("TURKEY", []))
    turkey_units_after = set(new_units.get("TURKEY", []))
    
    if turkey_units_before != turkey_units_after:
        print("\nTURKEY units changed positions!")
        print(f"Before: {turkey_units_before}")
        print(f"After: {turkey_units_after}")
    else:
        print("\nTURKEY units did not move.")

def test_order_submission():
    """Test different ways of submitting orders."""
    print_header("TESTING ORDER SUBMISSION METHODS")
    
    game = Game()
    print(f"Created new game, phase: {game.get_current_phase()}")
    
    # Get valid orders for Turkey
    all_orders = game.get_all_possible_orders()
    turkey_orders = all_orders.get("TURKEY", [])
    
    if not turkey_orders:
        print("No valid orders for TURKEY found!")
        return
    
    print(f"Found {len(turkey_orders)} valid orders for TURKEY")
    print("Sample orders:")
    for i, order in enumerate(turkey_orders[:5]):
        print(f"  {i+1}. {order}")
    
    # Try setting single orders
    print("\nTesting set_orders with a single order:")
    if turkey_orders:
        test_order = turkey_orders[0]
        try:
            game.set_orders("TURKEY", [test_order])
            print(f"Successfully set order: {test_order}")
        except Exception as e:
            print(f"Error setting order: {e}")
    
    # Try all methods we can think of to set orders
    methods = [
        lambda g: g.process(),
        lambda g: g.process_without_checks(),
        lambda g: g.process_with_retreat_decision({})
    ]
    
    print("\nTrying different processing methods:")
    for i, method in enumerate(methods):
        # Create a fresh game for each test
        test_game = Game()
        
        # Try to set some orders first
        if turkey_orders:
            try:
                test_game.set_orders("TURKEY", [turkey_orders[0]])
                print(f"\nTest {i+1}: Set orders: {turkey_orders[0]}")
            except Exception as e:
                print(f"\nTest {i+1}: Error setting orders: {e}")
        
        # Try the processing method
        try:
            method(test_game)
            print(f"Test {i+1}: Successfully processed game")
            
            # Check if phase changed
            new_phase = test_game.get_current_phase()
            print(f"Test {i+1}: New phase: {new_phase}")
            
            # Check if units moved
            state = test_game.get_state()
            print(f"Test {i+1}: Turkey units: {state.get('units', {}).get('TURKEY', [])}")
            
        except Exception as e:
            print(f"Test {i+1}: Error processing game: {e}")

def check_game_json():
    """Check if a saved game.json file exists and try to load it."""
    print_header("CHECKING SAVED GAME")
    
    if os.path.exists("game_state.json"):
        print("Found game_state.json, loading it...")
        try:
            with open("game_state.json", "r") as f:
                state_data = json.load(f)
            
            print("Successfully loaded game_state.json")
            print(f"Phase: {state_data.get('name', 'Unknown')}")
            
            # Try to create a game from this state
            try:
                game = Game(state_data)
                print("Successfully created game from state")
                
                # Inspect this game
                inspect_game_state(game)
                
            except Exception as e:
                print(f"Error creating game from state: {e}")
                
        except Exception as e:
            print(f"Error loading game_state.json: {e}")
    else:
        print("No game_state.json file found")

def main():
    print_header("DIPCC DEBUG")
    
    # Check for saved game
    check_game_json()
    
    # Test initial movement
    test_initial_movement()
    
    # Test order submission
    test_order_submission()

if __name__ == "__main__":
    main()