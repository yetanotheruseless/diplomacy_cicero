#!/usr/bin/env python3
"""
Script to play Diplomacy as Turkey using just the pydipcc module.
This avoids the dependencies required by the full fairdiplomacy codebase.
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
    for power, units in units_dict.items():
        print(f"{power}: {', '.join(units)}")

def print_centers(centers_dict):
    """Print supply centers in a formatted way."""
    for power, centers in centers_dict.items():
        print(f"{power}: {', '.join(centers)} ({len(centers)})")

def get_unit_orders(game, power, unit):
    """Get all possible orders for a specific unit."""
    all_orders = game.get_all_possible_orders().get(power, [])
    unit_orders = []
    for order in all_orders:
        parts = order.split()
        if len(parts) >= 2 and f"{parts[0]} {parts[1]}" == unit:
            unit_orders.append(order)
    return unit_orders

def select_random_orders(game, power):
    """Select random valid orders for a power."""
    all_orders = game.get_all_possible_orders().get(power, [])
    if not all_orders:
        return []
    
    # Group orders by unit
    orders_by_unit = {}
    for order in all_orders:
        parts = order.split()
        if len(parts) < 2:
            continue
        unit_key = f"{parts[0]} {parts[1]}"
        if unit_key not in orders_by_unit:
            orders_by_unit[unit_key] = []
        orders_by_unit[unit_key].append(order)
    
    # Select one random order per unit
    selected_orders = []
    for unit, unit_orders in orders_by_unit.items():
        selected_order = random.choice(unit_orders)
        selected_orders.append(selected_order)
        print(f"  {unit}: {selected_order}")
    
    return selected_orders

def load_game_from_json(file_path):
    """Load a game from a JSON file."""
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        game = Game(data)
        print(f"Loaded game from {file_path}")
        return game
    except Exception as e:
        print(f"Error loading game: {e}")
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
            if power == player_power:
                # Player's turn - get units and show possible orders
                units = state.get("units", {}).get(power, [])
                if not units:
                    print("  No units!")
                    continue
                
                print("  Your units:")
                for unit in units:
                    print(f"  - {unit}")
                
                print("\n  Selecting orders for your units:")
                selected_orders = []
                for unit in units:
                    unit_orders = get_unit_orders(game, power, unit)
                    if not unit_orders:
                        print(f"  - {unit}: No valid orders")
                        continue
                    
                    # For this script, just select a random order
                    # In a full implementation, you'd prompt for user input
                    selected_order = random.choice(unit_orders)
                    print(f"  - {unit}: {selected_order}")
                    selected_orders.append(selected_order)
                
                # Set the orders
                if selected_orders:
                    game.set_orders(power, selected_orders)
                    print(f"  Orders set for {power}: {selected_orders}")
                else:
                    print(f"  No orders for {power}")
            else:
                # AI power - select random orders
                print("  Selecting random orders:")
                orders = select_random_orders(game, power)
                if orders:
                    game.set_orders(power, orders)
                    print(f"  Orders set for {power}")
                else:
                    print(f"  No orders for {power}")
        
        # Process the game
        print_header("PROCESSING PHASE")
        try:
            game.process()
            print("Phase processed successfully!")
        except Exception as e:
            print(f"Error processing phase: {e}")
            break
        
        # Check for retreats
        if phase.endswith("R"):
            print("Retreat phase, processing automatically...")
            # In retreat phases, just process again without setting orders
            try:
                game.process()
                print("Retreat phase processed")
            except Exception as e:
                print(f"Error processing retreat: {e}")
        
        # Check if game is over
        if hasattr(game, "is_game_done") and game.is_game_done:
            print_header("GAME OVER")
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