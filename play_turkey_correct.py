#!/usr/bin/env python3
"""
Script to play Diplomacy as Turkey with correct order handling.
"""
import os
import sys
import argparse
import json
import random
from typing import Dict, List

# Ensure we can import pydipcc
try:
    from fairdiplomacy.pydipcc import Game
except ImportError:
    print("Error: pydipcc module not found. Make sure it's built and in the right location.")
    sys.exit(1)

# Constants
POWERS = ["AUSTRIA", "ENGLAND", "FRANCE", "GERMANY", "ITALY", "RUSSIA", "TURKEY"]

def print_header(title):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def print_units(units_dict):
    """Print units in a formatted way."""
    for power, units in sorted(units_dict.items()):
        print(f"{power}: {', '.join(units)}")

def print_centers(centers_dict):
    """Print supply centers in a formatted way."""
    for power, centers in sorted(centers_dict.items()):
        print(f"{power}: {', '.join(centers)} ({len(centers)})")

def get_units_possible_orders(game, power):
    """Get possible orders for all units of a power."""
    state = game.get_state()
    units = state.get("units", {}).get(power, [])
    
    # Get all possible orders from the game
    all_possible_orders = game.get_all_possible_orders()
    
    # Organize orders by unit
    units_orders = {}
    
    for unit in units:
        parts = unit.split()
        if len(parts) < 2:
            continue
            
        unit_type, unit_loc = parts[0], parts[1]
        
        # Look for orders for this unit location
        location_orders = all_possible_orders.get(unit_loc, [])
        
        # Filter orders that match this unit type
        matching_orders = []
        for order in location_orders:
            order_parts = order.split()
            if len(order_parts) >= 2 and order_parts[0] == unit_type:
                matching_orders.append(order)
        
        units_orders[unit] = matching_orders
    
    return units_orders

def select_strategic_order(orders):
    """Select a strategic order from a list of orders."""
    if not orders:
        return None
        
    # Categorize orders by type
    moves = []
    supports = []
    convoys = []
    holds = []
    
    for order in orders:
        if " - " in order:  # Move
            moves.append(order)
        elif " S " in order:  # Support
            supports.append(order)
        elif " C " in order:  # Convoy
            convoys.append(order)
        else:  # Hold
            holds.append(order)
    
    # Prefer more aggressive orders
    if moves:
        return random.choice(moves)
    elif supports:
        return random.choice(supports)
    elif convoys:
        return random.choice(convoys)
    elif holds:
        return random.choice(holds)
    
    return None

def load_game_from_json(file_path):
    """Load a game from a JSON file."""
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        game = Game()
        # Use the state for reference but we can't directly load it
        print(f"Created new game, referencing {file_path}")
        return game
    except Exception as e:
        print(f"Error with game file: {e}")
        return None

def save_game_to_json(game, file_path):
    """Save a game to a JSON file."""
    try:
        state = game.get_state()
        with open(file_path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"Saved game to {file_path}")
    except Exception as e:
        print(f"Error saving game: {e}")

def play_game(num_phases, player_power="TURKEY", load_file=None, save_file="game_state.json"):
    """Main function to play the game."""
    # Start a new game or load from file
    if load_file and os.path.exists(load_file):
        game = load_game_from_json(load_file)
        if not game:
            print("Creating a new game instead")
            game = Game()
    else:
        print("Starting a new game")
        game = Game()
    
    # Make sure player power is uppercase
    player_power = player_power.upper()
    if player_power not in POWERS:
        print(f"Invalid power '{player_power}'. Must be one of: {', '.join(POWERS)}")
        return
    
    print_header(f"PLAYING AS {player_power}")
    
    # Run the game for specified number of phases
    for phase_num in range(num_phases):
        phase = game.get_current_phase()
        print_header(f"PHASE {phase} (Turn {phase_num+1}/{num_phases})")
        
        # Get and display the current state
        state = game.get_state()
        print("UNITS:")
        print_units(state.get("units", {}))
        print("\nSUPPLY CENTERS:")
        print_centers(state.get("centers", {}))
        
        # Process orders for each power
        print_header("ORDERS")
        
        for power in POWERS:
            print(f"{power}:")
            
            # Get units and their possible orders
            units_orders = get_units_possible_orders(game, power)
            
            if not units_orders:
                print(f"  No units or no valid orders for {power}")
                continue
            
            selected_orders = []
            
            if power == player_power:
                # Player power - show options and make strategic choices
                print("  Your units:")
                for unit, orders in units_orders.items():
                    print(f"  - {unit}: {len(orders)} possible orders")
                    
                    # Show a sample of orders
                    categories = {"MOVE": [], "SUPPORT": [], "CONVOY": [], "HOLD": []}
                    for order in orders:
                        if " - " in order:
                            categories["MOVE"].append(order)
                        elif " S " in order:
                            categories["SUPPORT"].append(order)
                        elif " C " in order:
                            categories["CONVOY"].append(order)
                        else:
                            categories["HOLD"].append(order)
                    
                    # Print some samples of each category
                    for category, cat_orders in categories.items():
                        if cat_orders:
                            print(f"    {category}: {len(cat_orders)} orders")
                            for i, order in enumerate(cat_orders[:2]):
                                print(f"      {i+1}. {order}")
                            if len(cat_orders) > 2:
                                print(f"      ... and {len(cat_orders)-2} more")
                
                print("\n  Selecting strategic orders:")
                for unit, orders in units_orders.items():
                    order = select_strategic_order(orders)
                    if order:
                        print(f"  - {unit}: {order}")
                        selected_orders.append(order)
                    else:
                        print(f"  - {unit}: No suitable order found")
            else:
                # AI power - select orders automatically
                print("  Selecting orders:")
                for unit, orders in units_orders.items():
                    order = select_strategic_order(orders)
                    if order:
                        print(f"  - {unit}: {order}")
                        selected_orders.append(order)
            
            # Set the selected orders
            if selected_orders:
                game.set_orders(power, selected_orders)
                print(f"  Set {len(selected_orders)} orders for {power}")
            else:
                print(f"  No orders set for {power}")
        
        # Process the game
        print_header("PROCESSING PHASE")
        try:
            game.process()
            print("Phase processed successfully!")
        except Exception as e:
            print(f"Error processing phase: {e}")
            break
        
        # Save after each phase
        save_game_to_json(game, save_file)
    
    # Display final state
    print_header("FINAL STATE")
    final_state = game.get_state()
    print("UNITS:")
    print_units(final_state.get("units", {}))
    print("\nSUPPLY CENTERS:")
    print_centers(final_state.get("centers", {}))
    
    # Determine winner or leader
    centers = final_state.get("centers", {})
    if centers:
        leader = max(centers.items(), key=lambda x: len(x[1]))
        print(f"\nCurrent leader: {leader[0]} with {len(leader[1])} supply centers")
        if len(leader[1]) >= 18:
            print(f"GAME WON by {leader[0]}!")
    
    # Final save
    save_game_to_json(game, save_file)
    return game

def main():
    parser = argparse.ArgumentParser(description="Play Diplomacy as Turkey")
    parser.add_argument("--phases", type=int, default=8, help="Number of phases to play")
    parser.add_argument("--power", type=str, default="TURKEY", help="Power to play as")
    parser.add_argument("--load", type=str, help="Load game from JSON file")
    parser.add_argument("--save", type=str, default="game_state.json", help="Save game to JSON file")
    args = parser.parse_args()
    
    play_game(args.phases, args.power, args.load, args.save)

if __name__ == "__main__":
    main()