# Direct `pydipcc` Usage

Use this interface when you need the game engine without loading neural or
dialogue agents. It runs in the same supported Python 3.12 environment as the
rest of Cicero.

## Build and verify

```bash
make protos
make dipcc
python test_pydipcc.py
```

In Docker:

```bash
docker build --target cpu-build -t diplomacy-cicero:cpu .
docker run --rm diplomacy-cicero:cpu python test_pydipcc.py
```

## Create and advance a game

```python
from fairdiplomacy import pydipcc

game = pydipcc.Game()
print(game.current_short_phase)  # S1901M

game.set_orders(
    "AUSTRIA",
    ["A VIE - GAL", "A BUD - SER", "F TRI - ALB"],
)
game.process()
print(game.current_short_phase)
```

Orders not supplied for a power are handled according to the engine's normal
rules for that phase.

## Inspect legal orders

`get_orderable_locations()` maps powers to locations. Legal orders are indexed
by location:

```python
orderable = game.get_orderable_locations()
possible = game.get_all_possible_orders()

for power, locations in orderable.items():
    print(power)
    for location in locations:
        print(" ", location, possible[location])
```

## Serialize and clone

```python
payload = game.to_json()
restored = pydipcc.Game.from_json(payload)
assert restored.current_short_phase == game.current_short_phase

copy = pydipcc.Game(game)
batch = game.clone_n_times(8)
```

The JSON schema is documented in
[`docs/game_json_spec.md`](docs/game_json_spec.md).

## Scores and state

```python
state = game.get_state()
scores = dict(zip(
    ["AUSTRIA", "ENGLAND", "FRANCE", "GERMANY", "ITALY", "RUSSIA", "TURKEY"],
    game.get_scores(),
))

print(state["units"])
print(state["centers"])
print(scores)
```

## Agent-level usage

The direct engine does not choose orders. To use a configured agent:

```python
from fairdiplomacy.agents import build_agent_from_cfg
from fairdiplomacy.pydipcc import Game
import conf.agents_cfgs as agents_cfgs

agent = build_agent_from_cfg(
    agents_cfgs.Agent(random=agents_cfgs.RandomAgent()).to_frozen()
)
state = agent.initialize_state("FRANCE")
orders = agent.get_orders(Game(), "FRANCE", state)
print(orders)
```

Real strategy/dialogue agents additionally require the separately downloaded
model files.

## Troubleshooting

If import fails, verify the extension path and ABI:

```bash
find fairdiplomacy -maxdepth 1 -name 'pydipcc*.so' -print
python -c "from fairdiplomacy import pydipcc; print(pydipcc.__file__)"
```

Rebuild `pydipcc` after changing Python, PyTorch variant, architecture, or the
native toolchain.
