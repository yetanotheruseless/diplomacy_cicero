#!/usr/bin/env python3
"""
Minimal script to run a Diplomacy game using just the pydipcc module.
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
GAME_PHASES = ["S1901M", "S1901R", "F1901M", "F1901R", "S1902M", "S1902R", "F1902M", "F1902R"]

def select_random_orders(game: Game, power: str) -> List[str]:
    """Select random valid orders for a power."""
    possible_orders = game.get_all_possible_orders()
    if power not in possible_orders:
        return []
    
    power_orders = possible_orders[power]
    if not power_orders:
        return []
    
    # Group orders by unit
    orders_by_unit = {}
    for order in power_orders:
        parts = order.split()
        if len(parts) < 2:
            continue
        unit_loc = parts[1]
        if unit_loc not in orders_by_unit:
            orders_by_unit[unit_loc] = []
        orders_by_unit[unit_loc].append(order)
    
    # Select one random order per unit
    selected_orders = []
    for unit_loc, unit_orders in orders_by_unit.items():
        selected_orders.append(random.choice(unit_orders))
    
    return selected_orders

def play_game(num_phases: int, player_power: str = None, auto_all: bool = False):
    """Play a game for a specified number of phases."""
    print(f"Starting a new Diplomacy game")
    game = Game()
    
    player_power = player_power.upper() if player_power else random.choice(POWERS)
    print(f"You are playing as: {player_power}")
    
    for i in range(num_phases):
        phase = game.get_current_phase()
        print(f"\n=== Phase {phase} ===")
        
        # Get the state and print some information
        state = game.get_state()
        print(f"Centers: {state.get('centers', {})}")
        print(f"Units: {state.get('units', {})}")
        
        # Get all possible orders
        all_possible_orders = game.get_all_possible_orders()
        
        # Process orders for each power
        orders_dict = {}
        
        for power in POWERS:
            if power == player_power and not auto_all:
                # Player's power - show options and ask for input
                possible_orders = all_possible_orders.get(power, [])
                if possible_orders:
                    print(f"\nPossible orders for {power}:")
                    orders_by_unit = {}
                    for order in possible_orders:
                        parts = order.split()
                        if len(parts) < 2:
                            continue
                        unit_type, unit_loc = parts[0], parts[1]
                        key = f"{unit_type} {unit_loc}"
                        if key not in orders_by_unit:
                            orders_by_unit[key] = []
                        orders_by_unit[key].append(order)
                    
                    selected_orders = []
                    for unit, unit_orders in orders_by_unit.items():
                        print(f"\n{unit} can do:")
                        for i, order in enumerate(unit_orders):
                            print(f"  {i+1}. {order}")
                        
                        if len(unit_orders) == 1:
                            choice = 1
                            print(f"Only one option, automatically selecting: {unit_orders[0]}")
                        else:
                            # In interactive mode, we'd ask for input here
                            # For batch mode, just select randomly
                            choice = random.randint(1, len(unit_orders))
                            print(f"Selecting option {choice}: {unit_orders[choice-1]}")
                        
                        selected_orders.append(unit_orders[choice-1])
                    
                    orders_dict[power] = selected_orders
                    print(f"Orders for {power}: {selected_orders}")
                else:
                    print(f"No possible orders for {power}")
                    orders_dict[power] = []
            else:
                # AI power - select random orders
                orders = select_random_orders(game, power)
                orders_dict[power] = orders
                print(f"Orders for {power}: {orders}")
        
        # Process the orders
        try:
            game.process_orders(orders_dict)
            print(f"Orders processed successfully!")
        except Exception as e:
            print(f"Error processing orders: {e}")
            # Try to set orders instead
            try:
                for power, orders in orders_dict.items():
                    if orders:
                        print(f"Setting orders for {power}: {orders}")
                        game.set_orders(power, orders)
                game.process()
                print("Game processed after setting orders separately")
            except Exception as e2:
                print(f"Error setting orders and processing: {e2}")
                # Try to advance the game regardless
                try:
                    game.process()
                    print("Game advanced without orders")
                except Exception as e3:
                    print(f"Could not advance game: {e3}")
                    print("Game may be in an invalid state, stopping")
                    break
        
        # Check if game is over
        if game.is_game_done():
            print("\nGAME OVER!")
            break
    
    # Final state
    print("\n=== FINAL STATE ===")
    state = game.get_state()
    print(f"Centers: {state.get('centers', {})}")
    
    # Count supply centers
    centers_count = {power: len(centers) for power, centers in state.get('centers', {}).items()}
    print(f"Supply center count: {centers_count}")
    
    # Determine winner
    if any(count >= 18 for count in centers_count.values()):
        winner = max(centers_count, key=centers_count.get)
        print(f"WINNER: {winner} with {centers_count[winner]} supply centers!")
    else:
        print("No winner yet")
    
    return game

def main():
    parser = argparse.ArgumentParser(description="Run a minimal Diplomacy game")
    parser.add_argument("--phases", type=int, default=4, help="Number of phases to play")
    parser.add_argument("--power", type=str, default=None, help="Power to play as (default: random)")
    parser.add_argument("--auto", action="store_true", help="Automatic mode for all powers")
    args = parser.parse_args()
    
    game = play_game(args.phases, args.power, args.auto)
    
    # Save the final game state
    state = game.get_state()
    with open("game_state.json", "w") as f:
        json.dump(state, f, indent=2)
    print(f"Final game state saved to game_state.json")

if __name__ == "__main__":
    main()