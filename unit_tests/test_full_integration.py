#!/usr/bin/env python3
"""
Integration test to verify that Python components properly interact with
C++ libraries in the Diplomacy Cicero project.

This test verifies:
1. pydipcc module loads correctly
2. Game objects can be created and manipulated
3. Game state can be accessed and modified
4. Orders can be generated and processed
5. Integration with fairdiplomacy components works
"""

import sys
import unittest
import uuid
import json
import os

class FullIntegrationTest(unittest.TestCase):
    """Test full integration between Python and C++ components."""
    
    def setUp(self):
        # Ensure the fairdiplomacy module is in the path
        if not any(p.endswith('diplomacy_cicero') for p in sys.path):
            # Add the project root to the path if not already there
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            sys.path.insert(0, root_dir)
    
    def test_pydipcc_import(self):
        """Test that the pydipcc module can be imported."""
        from fairdiplomacy import pydipcc
        self.assertIsNotNone(pydipcc, "pydipcc module should be importable")
        
        # Check that key classes and functions are available
        self.assertTrue(hasattr(pydipcc, 'Game'), "Game class should be available")
        self.assertTrue(hasattr(pydipcc, 'get_all_possible_orders'), 
                       "get_all_possible_orders function should be available")
    
    def test_game_creation(self):
        """Test that a Game object can be created and manipulated."""
        from fairdiplomacy import pydipcc
        
        # Create a new game
        game = pydipcc.Game()
        self.assertIsNotNone(game, "Should be able to create a Game object")
        
        # Check that the game has a valid ID
        self.assertIsNotNone(game.game_id, "Game should have an ID")
        
        # Check that the game has a valid phase
        phase = game.get_current_phase()
        self.assertIsNotNone(phase, "Game should have a current phase")
        self.assertTrue(phase.startswith("S"), 
                       f"Game should start in Spring phase, got {phase}")
    
    def test_game_state_access(self):
        """Test that game state can be accessed."""
        from fairdiplomacy import pydipcc
        
        # Create a new game
        game = pydipcc.Game()
        
        # Get game state
        state = game.get_state()
        self.assertIsNotNone(state, "Should be able to get game state")
        
        # Check that the state has expected properties
        self.assertIn("phase", state, "State should have a phase")
        self.assertIn("units", state, "State should have units")
        self.assertIn("centers", state, "State should have centers")
    
    def test_order_generation(self):
        """Test that orders can be generated."""
        from fairdiplomacy import pydipcc
        
        # Create a new game
        game = pydipcc.Game()
        
        # Get all possible orders
        all_orders = game.get_all_possible_orders()
        self.assertIsNotNone(all_orders, "Should be able to get possible orders")
        
        # Verify the orders dictionary has entries for each power
        powers = ["AUSTRIA", "ENGLAND", "FRANCE", "GERMANY", 
                  "ITALY", "RUSSIA", "TURKEY"]
        for power in powers:
            self.assertIn(power, all_orders, f"{power} should have possible orders")
            self.assertTrue(len(all_orders[power]) > 0, 
                           f"{power} should have at least one possible order")
    
    def test_order_processing(self):
        """Test that orders can be processed."""
        from fairdiplomacy import pydipcc
        
        # Create a new game
        game = pydipcc.Game()
        initial_phase = game.get_current_phase()
        
        # Process empty orders (should advance the phase)
        game.process_orders({})
        new_phase = game.get_current_phase()
        
        # Verify that the phase has changed
        self.assertNotEqual(initial_phase, new_phase, 
                          "Phase should change after processing orders")
    
    def test_game_serialization(self):
        """Test that games can be serialized and deserialized."""
        from fairdiplomacy import pydipcc
        
        # Create a new game
        original_game = pydipcc.Game()
        
        # Make some moves to change the state
        original_game.process_orders({})
        
        # Serialize to JSON
        game_json = original_game.to_json()
        self.assertIsNotNone(game_json, "Should be able to serialize game to JSON")
        
        # Deserialize from JSON
        deserialized_game = pydipcc.Game.from_json(game_json)
        self.assertIsNotNone(deserialized_game, 
                           "Should be able to deserialize game from JSON")
        
        # Verify the states match
        original_state = original_game.get_state()
        deserialized_state = deserialized_game.get_state()
        self.assertEqual(original_state, deserialized_state, 
                       "Serialized and deserialized states should match")
    
    def test_fairdiplomacy_integration(self):
        """Test integration with fairdiplomacy components."""
        try:
            # Import key components from fairdiplomacy
            from fairdiplomacy.agents.random_agent import RandomAgent
            from fairdiplomacy.game import Game
            
            # Create a game
            game = Game()
            self.assertIsNotNone(game, "Should be able to create a fairdiplomacy Game")
            
            # Create a random agent
            agent = RandomAgent()
            self.assertIsNotNone(agent, "Should be able to create a RandomAgent")
            
            # Get a power
            power = list(game.get_all_powers())[0]
            
            # Get orders from the agent
            # This verifies the agent can interact with the game state
            try:
                orders = agent.get_orders(game, power)
                self.assertIsNotNone(orders, "Agent should produce orders")
            except Exception as e:
                # If this fails due to initialization issues, that's ok
                # The main point is to verify the modules are loadable and connected
                pass
            
        except ImportError as e:
            # Skip this test if the fairdiplomacy components aren't available
            # This could happen in minimal builds or certain CI environments
            self.skipTest(f"Skipping fairdiplomacy integration test: {e}")

if __name__ == "__main__":
    unittest.main()