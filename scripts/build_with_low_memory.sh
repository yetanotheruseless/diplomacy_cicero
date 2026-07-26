#!/bin/bash
# Script to build the project with lower memory usage

# Clean previous build
echo "Cleaning previous build..."
make clean

# Compile protocol buffers
echo "Compiling protocol buffers..."
make protos_basic

# Build dipcc with only 1 job
echo "Building dipcc with minimal memory usage..."
cd dipcc && PYDIPCC_OUT_DIR=/app/fairdiplomacy SKIP_TESTS=1 JOBS=1 ./compile.sh && cd ..

# Test if the dipcc module is usable
echo "Testing dipcc module..."
cat > test_dipcc.py << 'EOF'
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
EOF

python test_dipcc.py

echo
echo "If the tests above were successful, the core game engine is working."
echo "You can try creating and running a minimal game directly without using heyhi/run.py."