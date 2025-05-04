# Direct Usage Guide for Diplomacy Cicero

If you're encountering issues with the standard `run.py` approach (which uses the heyhi framework), this guide provides an alternative method to use the core game engine directly.

## Prerequisites

- Docker environment set up as described in the main README
- Downloaded model files (optional, only if you want to use the advanced agents)

## Using the Core Game Engine

### 1. Build the Core Game Engine

We've created a specialized build script that builds just the essential C++ components:

```bash
cd /app
./build_minimal.sh
```

This will build the dipcc C++ library and provide the core game engine functionality.

### 2. Run a Simple Game

Once the build is complete, you can use the direct interface:

```bash
python run_simple_game.py
```

This script:
- Creates a new Diplomacy game
- Shows game state information
- Lists possible orders for each power
- Demonstrates how to save and load games from JSON

### 3. Programmatic Interface

You can interact with the game engine directly in your Python code:

```python
# Import the Game class from our custom package
from dipcc_pkg import Game

# Create a new game
game = Game()

# Get the current phase
current_phase = game.get_current_phase()
print(f"Current phase: {current_phase}")

# Get all possible orders
orders = game.get_all_possible_orders()
for power, power_orders in orders.items():
    print(f"{power} has {len(power_orders)} possible orders")

# Save game to JSON
json_state = game.to_json()
with open("game_state.json", "w") as f:
    f.write(json_state)

# Load game from JSON
with open("game_state.json", "r") as f:
    json_state = f.read()
loaded_game = Game.from_json(json_state)
```

### 4. Available Methods

The Game object provides these key methods:

- `game.get_current_phase()` - Get the current game phase
- `game.get_state()` - Get the current game state
- `game.get_all_possible_orders()` - Get all possible orders for each location
- `game.to_json()` - Serialize the game to JSON
- `Game.from_json(json_str)` - Create a game from JSON (static method)

### 5. Limitations

When using the direct interface:

- You won't have access to the AI agents or dialogue functionality
- The full initialization/advancement API is limited
- You'll need to implement your own logic for things like turns and orders processing

## For Advanced Users

### Setting Orders

To set orders for a power and process them:

```python
# Example based on the API we observed
for power in ["FRANCE", "ENGLAND", "RUSSIA", "GERMANY", "AUSTRIA", "ITALY", "TURKEY"]:
    # Set hold orders for all units of this power
    # Note: The exact API parameters may need adjustment based on what's available
    try:
        # You'll need to figure out the exact parameter format based on the error messages
        game.set_orders(power, ["A PAR H", "F BRE H"])  # Example orders
    except Exception as e:
        print(f"Error setting orders for {power}: {e}")
```

### Advanced Visualization

To visualize games, you can use the HTML visualizer in `fairdiplomacy_external`:

```bash
python fairdiplomacy_external/game_to_html.py game_state.json
```

## Troubleshooting

If you encounter issues:

1. Check the available methods on the Game object:
   ```python
   methods = [m for m in dir(game) if not m.startswith('_')]
   print(methods)
   ```

2. For detailed error messages, use:
   ```python
   import traceback
   try:
       # Your code here
   except Exception as e:
       print(f"Error: {e}")
       traceback.print_exc()
   ```

3. If you need to rebuild the core components, clean first:
   ```bash
   make clean
   ./build_minimal.sh
   ```