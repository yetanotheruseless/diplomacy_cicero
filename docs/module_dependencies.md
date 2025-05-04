# Module Dependencies Diagram

This document provides a visual representation of the module dependencies in the Diplomacy Cicero project, with a focus on the relationship between dipcc and fairdiplomacy.pydipcc.

## Component Architecture

The diagram below shows the main components and their relationships:

```mermaid
graph TD
    subgraph "C++ Components"
        dipcc[dipcc C++ Library]
        pybind[pybind11 Bindings]
        so[pydipcc.*.so Shared Object]
    end
    
    subgraph "Python Components"
        fair_init[fairdiplomacy/__init__.py]
        pydipcc[fairdiplomacy.pydipcc]
        agents[fairdiplomacy/agents/]
        models[fairdiplomacy/models/]
        parlai[parlai_diplomacy/]
    end
    
    dipcc --> pybind
    pybind --> so
    so --> fair_init
    fair_init --> pydipcc
    
    pydipcc --> agents
    pydipcc --> models
    agents --> parlai
    
    classDef cpp fill:#f96,stroke:#333,stroke-width:2px
    classDef py fill:#6af,stroke:#333,stroke-width:2px
    
    class dipcc,pybind,so cpp
    class fair_init,pydipcc,agents,models,parlai py
```

## Build and Import Flow

This diagram shows the build and import process:

```mermaid
sequenceDiagram
    participant CMake as CMake/Make
    participant Compiler as C++ Compiler
    participant Python as Python Runtime
    participant FairInit as fairdiplomacy/__init__.py
    
    CMake ->> Compiler: Configure build
    Compiler ->> CMake: Create pydipcc.*.so
    CMake ->> Python: Copy .so to fairdiplomacy/
    
    Python ->> FairInit: Import fairdiplomacy
    FairInit ->> FairInit: Try direct dipcc import
    alt Direct import succeeds
        FairInit ->> Python: Alias dipcc to fairdiplomacy.pydipcc
    else Direct import fails
        FairInit ->> FairInit: Search for pydipcc*.so files
        FairInit ->> Python: Load .so file with importlib
    end
    Python ->> Python: Register fairdiplomacy.pydipcc
```

## Module Structure

This diagram shows the internal structure of the dipcc C++ library:

```mermaid
classDiagram
    class Game {
        +string game_id
        +string current_short_phase
        +Game()
        +Game(json_state)
        +get_state()
        +process_orders(orders)
        +get_all_possible_orders()
        +get_phase_history()
        +to_json()
    }
    
    class GameState {
        +string phase
        +map~string,Power~ powers
        +map~string,Unit~ units
        +bool is_terminal()
    }
    
    class Power {
        +string name
        +list~string~ units
        +list~string~ centers
        +list~string~ homes
    }
    
    class Order {
        +string unit_type
        +string source
        +string dest
        +string order_type
        +string target
        +bool is_valid()
    }
    
    Game "1" *-- "1" GameState: has
    GameState "1" *-- "*" Power: contains
    GameState "1" *-- "*" Order: validates
```

## Data Flow

This diagram shows the data flow during a typical game simulation:

```mermaid
flowchart LR
    input[Game Configuration]
    game[pydipcc.Game]
    orders[Order Generation]
    state[Game State]
    output[Results]
    
    input --> game
    game --> state
    state --> orders
    orders --> game
    game --> output
    
    style input fill:#f9f,stroke:#333,stroke-width:1px
    style output fill:#f9f,stroke:#333,stroke-width:1px
```

## Cross-Platform Compatibility

This diagram illustrates the platform-specific module loading process:

```mermaid
graph TD
    build[Build Process]
    build --> x86[pydipcc.cpython-38-x86_64-linux-gnu.so]
    build --> arm[pydipcc.cpython-38-aarch64-linux-gnu.so]
    build --> mac[pydipcc.cpython-38-darwin.so]
    
    glob{Glob Pattern Matching}
    x86 --> glob
    arm --> glob
    mac --> glob
    
    glob --> loader[Dynamic Module Loader]
    loader --> module[fairdiplomacy.pydipcc]
    
    style build fill:#f96,stroke:#333,stroke-width:2px
    style glob fill:#6af,stroke:#333,stroke-width:2px
    style loader fill:#6af,stroke:#333,stroke-width:2px
    style module fill:#6af,stroke:#333,stroke-width:2px
```

These diagrams provide a visual representation of the module dependencies and interactions in the Diplomacy Cicero project. They can be rendered using tools that support the Mermaid diagram syntax.