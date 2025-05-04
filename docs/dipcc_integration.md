# dipcc and fairdiplomacy.pydipcc Integration

This document explains the relationship between the `dipcc` C++ library and the `fairdiplomacy.pydipcc` Python module in the Diplomacy Cicero project.

## Overview

The Diplomacy Cicero project uses a hybrid architecture:

1. **C++ Game Engine (dipcc)**: Implements the core game rules, state management, and order validation
2. **Python Interface (fairdiplomacy.pydipcc)**: Provides Python bindings to the C++ engine
3. **AI Components (fairdiplomacy)**: Implements the strategic reasoning and natural language capabilities

This separation allows for high performance in the game logic while enabling easy integration with Python-based machine learning frameworks.

## Module Structure

### 1. dipcc (C++ Library)

The `dipcc` directory contains the C++ implementation of the Diplomacy game engine:

```
dipcc/
  ├── CMakeLists.txt            # Build configuration
  ├── dipcc/                    # Core implementation
  │   ├── cc/                   # C++ source files
  │   │   ├── game.h/cc         # Game class implementation
  │   │   ├── game_state.h/cc   # Game state representation
  │   │   ├── order.h/cc        # Order representation and validation
  │   │   └── ...
  │   ├── pybind/                # Python binding code
  │   │   ├── pybind.cc         # Main binding definitions
  │   │   └── ...
  │   └── profiling/            # Performance measurement tools
  └── compile.sh                # Compilation script
```

The C++ code is compiled into a shared library (`.so` file) that can be loaded by Python.

### 2. fairdiplomacy.pydipcc (Python Module)

The Python interface to the C++ library is provided through the `fairdiplomacy.pydipcc` module. This is not a separate Python package, but rather a dynamic module created at build time.

There are **three ways** this module becomes available:

1. **Direct Import**: If the `dipcc` module is properly installed as a Python package, it can be directly imported and aliased:
   ```python
   import dipcc
   sys.modules["fairdiplomacy.pydipcc"] = dipcc
   ```

2. **Manual Loading**: The compiled `.so` file can be directly loaded using Python's importlib:
   ```python
   so_path = "path/to/pydipcc.cpython-XX-ARCH-OS.so"
   spec = importlib.util.spec_from_file_location("pydipcc", so_path)
   pydipcc = importlib.util.module_from_spec(spec)
   spec.loader.exec_module(pydipcc)
   sys.modules["fairdiplomacy.pydipcc"] = pydipcc
   ```

3. **Dynamic Discovery**: The improved loading mechanism searches for `.so` files with platform-specific names:
   ```python
   so_files = glob.glob("fairdiplomacy/pydipcc*.so")
   # Load the first one found
   ```

## Module Loading Process

The loading process happens in `fairdiplomacy/__init__.py` and follows these steps:

1. First try direct import of the dipcc module (pre-installed package)
2. If that fails, search for .so files with a pydipcc* pattern in the expected locations
3. Load the first matching .so file using Python's importlib
4. If all methods fail, raise an error

## Integration Points

The integration between the C++ and Python components occurs at several points:

### 1. Game State Representation

The C++ game state is exposed to Python through the `Game` class:

```python
from fairdiplomacy import pydipcc
game = pydipcc.Game()  # Create a new game
state = game.get_state()  # Get the current game state
```

### 2. Order Validation and Processing

Orders are validated and processed by the C++ engine:

```python
valid_orders = game.get_all_possible_orders()  # Get all valid orders
game.process_orders(orders_dict)  # Process a set of orders
```

### 3. Data Serialization

Game states can be serialized to/from JSON for storage and transmission:

```python
json_state = game.to_json()  # Serialize game to JSON
new_game = pydipcc.Game.from_json(json_state)  # Create game from JSON
```

## Build Process

The integration is established during the build process:

1. The C++ code is compiled into a shared library using CMake
2. The resulting `.so` file is copied to the `fairdiplomacy/` directory
3. The `fairdiplomacy/__init__.py` file is configured to load this library

## Cross-Platform Considerations

The name of the compiled `.so` file includes platform-specific information:

```
pydipcc.cpython-38-x86_64-linux-gnu.so  # Example for x86_64 Linux
pydipcc.cpython-38-aarch64-linux-gnu.so  # Example for ARM64 Linux
```

The dynamic loading mechanism handles these platform differences by using glob patterns to find the appropriate file.

## Troubleshooting

If you encounter issues with the dipcc/pydipcc integration:

1. Verify that the `.so` file exists in the fairdiplomacy directory
2. Run the test script: `python test_pydipcc.py`
3. Check for platform compatibility issues
4. Ensure the correct build steps were followed

## Further Reading

- [DIPCC_BUILD_NOTES.md](../DIPCC_BUILD_NOTES.md) for detailed build instructions
- [CMakeLists.txt](../dipcc/CMakeLists.txt) for the build configuration
- [test_pydipcc.py](../test_pydipcc.py) for validation testing