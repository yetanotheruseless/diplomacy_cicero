#!/usr/bin/env python3
"""Smoke-test the built pydipcc extension through its supported public API."""

import platform

from fairdiplomacy import pydipcc

POWERS = ("AUSTRIA", "ENGLAND", "FRANCE", "GERMANY", "ITALY", "RUSSIA", "TURKEY")


def main() -> None:
    print(f"Python: {platform.python_version()}")
    print(f"Platform: {platform.platform()} ({platform.machine()})")
    print(f"pydipcc: {pydipcc.__file__}")

    game = pydipcc.Game()
    assert game.current_short_phase == "S1901M"
    assert game.get_current_phase() == game.current_short_phase

    state = game.get_state()
    assert state["name"] == "S1901M"
    assert set(state["units"]) == set(POWERS)
    assert set(state["centers"]) == set(POWERS)

    possible_orders = game.get_all_possible_orders()
    orderable_locations = game.get_orderable_locations()
    assert set(orderable_locations) == set(POWERS)
    assert possible_orders
    for power, locations in orderable_locations.items():
        assert locations, f"{power} has no orderable locations"
        for location in locations:
            assert possible_orders.get(location), f"{location} has no possible orders"

    initial_phase = game.current_short_phase
    game.process()
    assert initial_phase == "S1901M"
    assert game.current_short_phase == "F1901M"

    restored = pydipcc.Game.from_json(game.to_json())
    assert restored.current_short_phase == game.current_short_phase
    assert restored.get_state() == game.get_state()

    print(
        "pydipcc smoke passed:",
        f"{len(possible_orders)} orderable map locations,",
        f"phase {initial_phase} -> {game.current_short_phase},",
        "JSON round-trip exact",
    )


if __name__ == "__main__":
    main()
