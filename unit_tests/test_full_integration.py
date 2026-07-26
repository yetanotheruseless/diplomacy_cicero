#!/usr/bin/env python3
"""Integration tests for the Python-to-pydipcc boundary."""

import unittest

from fairdiplomacy import pydipcc

POWERS = ("AUSTRIA", "ENGLAND", "FRANCE", "GERMANY", "ITALY", "RUSSIA", "TURKEY")


class FullIntegrationTest(unittest.TestCase):
    """Verify the public pydipcc game API used by fairdiplomacy."""

    def test_pydipcc_import(self):
        self.assertTrue(hasattr(pydipcc, "Game"))
        self.assertTrue(hasattr(pydipcc.Game, "get_all_possible_orders"))

    def test_game_creation(self):
        game = pydipcc.Game()

        self.assertTrue(game.game_id)
        self.assertEqual(game.current_short_phase, "S1901M")
        self.assertEqual(game.get_current_phase(), game.current_short_phase)

    def test_game_state_access(self):
        state = pydipcc.Game().get_state()

        self.assertEqual(state["name"], "S1901M")
        self.assertEqual(set(state["units"]), set(POWERS))
        self.assertEqual(set(state["centers"]), set(POWERS))

    def test_order_generation(self):
        game = pydipcc.Game()
        possible_orders = game.get_all_possible_orders()
        orderable_locations = game.get_orderable_locations()

        self.assertEqual(set(orderable_locations), set(POWERS))
        for power, locations in orderable_locations.items():
            self.assertTrue(locations, f"{power} should have orderable locations")
            for location in locations:
                self.assertIn(location, possible_orders)
                self.assertTrue(
                    possible_orders[location],
                    f"{location} should have at least one possible order",
                )

    def test_order_processing(self):
        game = pydipcc.Game()
        initial_phase = game.current_short_phase

        game.process()

        self.assertNotEqual(initial_phase, game.current_short_phase)
        self.assertEqual(game.current_short_phase, "F1901M")

    def test_game_serialization(self):
        original_game = pydipcc.Game()
        original_game.process()

        deserialized_game = pydipcc.Game.from_json(original_game.to_json())

        self.assertEqual(original_game.current_short_phase, deserialized_game.current_short_phase)
        self.assertEqual(original_game.get_state(), deserialized_game.get_state())


if __name__ == "__main__":
    unittest.main()
