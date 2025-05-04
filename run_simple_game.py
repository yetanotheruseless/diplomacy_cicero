#!/usr/bin/env python3
"""
Simple script to create and run a Diplomacy game.

This script provides a basic example of using the Diplomacy Cicero
game engine directly, bypassing the run.py framework which requires
the heyhi module.
"""
import os
import sys
import json

def setup_dipcc_pkg():
    """Set up the dipcc_pkg to make the Game class available."""
    # Run our fix script if the dipcc_pkg doesn't exist
    if not os.path.exists("dipcc_pkg"):
        print("Setting up dipcc_pkg...")
        import fix_dipcc_load
        fix_dipcc_load.main()
    
    # Make sure dipcc_pkg is in the Python path
    package_path = os.path.abspath("dipcc_pkg")
    if os.path.dirname(package_path) not in sys.path:
        sys.path.insert(0, os.path.dirname(package_path))

def create_game():
    """Create a new Diplomacy game."""
    from dipcc_pkg import Game
    return Game()

def print_game_state(game):
    """Print the current game state."""
    print(f"Game ID: {game.game_id}")
    print(f"Current phase: {game.get_current_phase()}")
    
    try:
        # Get the state
        state = game.get_state()
        print(f"\nGame state summary:")
        print(f"  State type: {type(state)}")
        
        # Just print the available attributes and methods
        print("\nAvailable methods on game object:")
        methods = [m for m in dir(game) if not m.startswith('_')]
        print(f"  {', '.join(methods[:10])}...")
        
        # Try getting a list of powers
        try:
            powers = game.get_powers()
            print(f"\nPowers in the game: {powers}")
        except Exception as e:
            print(f"Error getting powers: {e}")
    except Exception as e:
        print(f"Error getting game state: {e}")
        import traceback
        traceback.print_exc()

def print_possible_orders(game):
    """Print the possible orders for each power."""
    orders = game.get_all_possible_orders()
    
    print("\nNumber of possible orders by power:")
    for power, power_orders in orders.items():
        print(f"  {power}: {len(power_orders)} possible orders")
        
        # Print a few examples
        if len(power_orders) > 0:
            print("  Examples:")
            for i, order in enumerate(power_orders[:3]):
                print(f"    {i+1}. {order}")
            if len(power_orders) > 3:
                print(f"    ... and {len(power_orders)-3} more")

def process_empty_orders(game):
    """Process empty orders to advance the game state."""
    prev_phase = game.get_current_phase()
    print(f"\nAdvancing from phase {prev_phase}...")
    
    try:
        # Check what method is available to process orders
        methods = dir(game)
        
        if "process_orders" in methods:
            # Process empty orders (all powers hold)
            game.process_orders({})
        elif "set_orders" in methods:
            # Try set_orders method instead
            game.set_orders({})
            game.process()
        elif "process" in methods:
            # Just try process
            game.process()
        else:
            print("No method found to process orders")
            return False
        
        new_phase = game.get_current_phase()
        print(f"Advanced to phase {new_phase}")
        
        return new_phase != prev_phase
    except Exception as e:
        print(f"Error processing orders: {e}")
        import traceback
        traceback.print_exc()
        return False

def save_game_to_json(game, filename="game_state.json"):
    """Save the game state to a JSON file."""
    json_state = game.to_json()
    with open(filename, "w") as f:
        f.write(json_state)
    print(f"\nGame state saved to {filename}")

def load_game_from_json(filename="game_state.json"):
    """Load a game from a JSON file."""
    if not os.path.exists(filename):
        print(f"Error: File {filename} not found")
        return None
    
    with open(filename, "r") as f:
        json_state = f.read()
    
    from dipcc_pkg import Game
    return Game.from_json(json_state)

def main():
    """Main function to run a simple game."""
    # Set up the dipcc_pkg
    setup_dipcc_pkg()
    
    # Create a new game
    print("Creating a new Diplomacy game...")
    game = create_game()
    
    # Print the initial state
    print_game_state(game)
    
    # Print possible orders
    print_possible_orders(game)
    
    # Process orders for a few phases
    for _ in range(3):
        if not process_empty_orders(game):
            print("Game has reached a terminal state, stopping.")
            break
    
    # Print the final state
    print("\nFinal game state:")
    print_game_state(game)
    
    # Save the game
    save_game_to_json(game)
    
    # Load the game back
    print("\nLoading game from JSON...")
    loaded_game = load_game_from_json()
    if loaded_game:
        print("Successfully loaded game from JSON")
        print(f"Loaded game phase: {loaded_game.get_current_phase()}")
    
    print("\nSimple game run completed successfully!")
    return True

if __name__ == "__main__":
    main()