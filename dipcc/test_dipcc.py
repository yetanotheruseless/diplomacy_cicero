try:
    # Try importing through fairdiplomacy
    from fairdiplomacy import pydipcc
    print("✅ Successfully imported fairdiplomacy.pydipcc")
    
    # Try creating a game
    game = pydipcc.Game()
    print(f"✅ Successfully created a game with ID: {game.game_id}")
    print(f"Current phase: {game.get_current_phase()}")
    
    # Try getting all possible orders
    orders = game.get_all_possible_orders()
    print(f"✅ Got {sum(len(orders_list) for orders_list in orders.values())} possible orders")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
