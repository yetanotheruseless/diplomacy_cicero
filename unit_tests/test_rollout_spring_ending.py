#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
import random
from typing import List
import unittest

import torch
from fairdiplomacy.agents.base_strategy_model_rollouts import BaseStrategyModelRollouts
from fairdiplomacy.agents.base_strategy_model_wrapper import BaseStrategyModelWrapper
from fairdiplomacy.game import POWERS
from fairdiplomacy.models.base_strategy_model.base_strategy_model import Scoring
from fairdiplomacy.models.base_strategy_model.mock_base_strategy_model import MockBaseStrategyModel
from fairdiplomacy.pydipcc import Game
from fairdiplomacy.typedefs import JointAction
import heyhi.conf
import numpy as np

import conf.agents_cfgs


class TestRolloutSpringEnding(unittest.TestCase):
    def _test_helper(
        self, game: Game, max_rollout_length, year_spring_prob_of_ending, n=5, random_orders=False
    ):
        # These rollout snapshots intentionally pin Torch 2.13's multinomial stream.
        torch.manual_seed(12345)
        random.seed(12345)
        cfg = conf.agents_cfgs.BaseStrategyModelRollouts(
            n_threads=1,
            temperature=1.0,
            top_p=1.0,
            max_rollout_length=max_rollout_length,
            average_n_rollouts=1,
            mix_square_ratio_scoring=0.0,
            clear_old_all_possible_orders=False,
            has_press=False,
            year_spring_prob_of_ending=year_spring_prob_of_ending,
        )
        base_strategy_model = BaseStrategyModelWrapper("MOCKV3")
        # Force model to say Austria is winning.
        base_strategy_model.model = MockBaseStrategyModel(  # type:ignore
            input_version=3, fixed_value_output=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        )
        base_strategy_model.value_model = MockBaseStrategyModel(  # type:ignore
            input_version=3, fixed_value_output=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        )
        base_strategy_model_rollouts = BaseStrategyModelRollouts(
            base_strategy_model, cfg, has_press=False
        )

        set_orders_dicts: List[JointAction] = [{power: () for power in POWERS} for i in range(n)]
        if random_orders:
            for i in range(n):
                power_locs = game.get_orderable_locations()
                for power in power_locs:
                    orders = []
                    for loc in power_locs[power]:
                        order = random.choice(game.get_all_possible_orders()[loc])
                        orders.append(order)
                    set_orders_dicts[i][power] = tuple(orders)

        results = base_strategy_model_rollouts.do_rollouts(
            game, agent_power=None, set_orders_dicts=set_orders_dicts
        )
        return results

    def test_roll0_baseline(self):
        game = Game()
        results = self._test_helper(game, max_rollout_length=0, year_spring_prob_of_ending=None)
        for (jointaction, jointactionvalues) in results:
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)
            assert np.allclose(jointactionvalues, [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    # Nothing happens since rollout 0 from spring doesn't reach next spring
    def test_roll0_30pct(self):
        game = Game()
        results = self._test_helper(
            game, max_rollout_length=0, year_spring_prob_of_ending="1901,0.3"
        )
        for (jointaction, jointactionvalues) in results:
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)
            assert np.allclose(jointactionvalues, [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    # Nothing happens since rollout 1 from spring doesn't reach next spring
    def test_roll1_30pct(self):
        game = Game()
        results = self._test_helper(
            game, max_rollout_length=1, year_spring_prob_of_ending="1901,0.3"
        )
        for (jointaction, jointactionvalues) in results:
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)
            assert np.allclose(jointactionvalues, [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    def test_roll2_30pct(self):
        game = Game()
        results = self._test_helper(
            game, max_rollout_length=2, year_spring_prob_of_ending="1901,0.3"
        )
        for i, (jointaction, jointactionvalues) in enumerate(results):
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)

            # Rollout 2 crosses over spring, so we see
            # now taking into account the game ending in spring with 30% chance.
            # Some of them are different because the players win/lose some SCs.
            expected = [
                [
                    0.7350649,
                    0.035064936,
                    0.035064936,
                    0.035064936,
                    0.062337663,
                    0.062337663,
                    0.035064936,
                ],
                [
                    0.7623376,
                    0.035064936,
                    0.035064936,
                    0.035064936,
                    0.035064936,
                    0.062337663,
                    0.035064936,
                ],
                [
                    0.7350649,
                    0.035064936,
                    0.035064936,
                    0.062337663,
                    0.035064936,
                    0.062337663,
                    0.035064936,
                ],
                [
                    0.75714284,
                    0.03214286,
                    0.03214286,
                    0.057142857,
                    0.03214286,
                    0.057142857,
                    0.03214286,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
            ]
            assert np.allclose(jointactionvalues, expected[i])

    def test_roll2_30pct_1902(self):
        game = Game()
        results = self._test_helper(
            game, max_rollout_length=2, year_spring_prob_of_ending="1902,0.3"
        )
        for i, (jointaction, jointactionvalues) in enumerate(results):
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)

            # Ending 1902 is the same, doesn't matter
            expected = [
                [
                    0.7350649,
                    0.035064936,
                    0.035064936,
                    0.035064936,
                    0.062337663,
                    0.062337663,
                    0.035064936,
                ],
                [
                    0.7623376,
                    0.035064936,
                    0.035064936,
                    0.035064936,
                    0.035064936,
                    0.062337663,
                    0.035064936,
                ],
                [
                    0.7350649,
                    0.035064936,
                    0.035064936,
                    0.062337663,
                    0.035064936,
                    0.062337663,
                    0.035064936,
                ],
                [
                    0.75714284,
                    0.03214286,
                    0.03214286,
                    0.057142857,
                    0.03214286,
                    0.057142857,
                    0.03214286,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
            ]
            assert np.allclose(jointactionvalues, expected[i])

    def test_roll2_30pct_1903(self):
        game = Game()
        results = self._test_helper(
            game, max_rollout_length=2, year_spring_prob_of_ending="1903,0.3"
        )
        for i, (jointaction, jointactionvalues) in enumerate(results):
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)

            # Ending 1903 then nothing happens since we don't reach it.
            expected = [
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            ]
            assert np.allclose(jointactionvalues, expected[i])

    def test_fall_roll0_30pct(self):
        game = Game()
        game.set_orders("ITALY", ("F NAP - ION",))
        game.set_orders("RUSSIA", ("A WAR - GAL",))
        game.set_orders("AUSTRIA", ("F TRI - ADR",))
        game.process()
        results = self._test_helper(
            game, max_rollout_length=0, year_spring_prob_of_ending="1901,0.3", n=5
        )
        for i, (jointaction, jointactionvalues) in enumerate(results):
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)

            # Rollout 0 from fall reaches next spring
            expected = [
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.06857143,
                    0.038571432,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.06857143,
                    0.038571432,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.06857143,
                    0.038571432,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.06857143,
                    0.038571432,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.06857143,
                    0.038571432,
                ],
            ]
            assert np.allclose(jointactionvalues, expected[i])

    def test_fall_roll0_30pct_dss(self):
        game = Game()
        game.set_scoring_system(Game.SCORING_DSS)
        game.set_orders("ITALY", ("F NAP - ION",))
        game.set_orders("RUSSIA", ("A WAR - GAL",))
        game.set_orders("AUSTRIA", ("F TRI - ADR",))
        game.process()
        results = self._test_helper(
            game, max_rollout_length=0, year_spring_prob_of_ending="1901,0.3", n=5
        )
        for i, (jointaction, jointactionvalues) in enumerate(results):
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)

            # Rollout 0 from fall reaches next spring, dss
            expected = [
                [
                    0.74285716,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                ],
                [
                    0.74285716,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                ],
                [
                    0.74285716,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                ],
                [
                    0.74285716,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                ],
                [
                    0.74285716,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                    0.042857144,
                ],
            ]
            assert np.allclose(jointactionvalues, expected[i])

    def test_fall_roll0_30pct_rand(self):
        game = Game()
        game.set_orders("ITALY", ("F NAP - ION",))
        game.set_orders("RUSSIA", ("A WAR - GAL",))
        game.set_orders("AUSTRIA", ("F TRI - ADR",))
        game.process()
        results = self._test_helper(
            game,
            max_rollout_length=0,
            year_spring_prob_of_ending="1901,0.3",
            random_orders=True,
            n=10,
        )
        for i, (jointaction, jointactionvalues) in enumerate(results):
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)

            # Rollout 0 from fall doesn't always reach next spring with random orders, sometimes we get a build.
            expected = [
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            ]
            assert np.allclose(jointactionvalues, expected[i])

    def test_fall_roll1_30pct_rand(self):
        game = Game()
        game.set_orders("ITALY", ("F NAP - ION",))
        game.set_orders("RUSSIA", ("A WAR - GAL",))
        game.set_orders("AUSTRIA", ("F TRI - ADR",))
        game.process()
        results = self._test_helper(
            game,
            max_rollout_length=1,
            year_spring_prob_of_ending="1901,0.3",
            random_orders=True,
            n=10,
        )
        for i, (jointaction, jointactionvalues) in enumerate(results):
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)

            # Rollout 1 from fall reaches next spring with random orders.
            expected = [
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
                [
                    0.73417723,
                    0.034177214,
                    0.034177214,
                    0.034177214,
                    0.034177214,
                    0.094936706,
                    0.034177214,
                ],
                [
                    0.7350649,
                    0.035064936,
                    0.035064936,
                    0.062337663,
                    0.035064936,
                    0.062337663,
                    0.035064936,
                ],
                [
                    0.7385714,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.038571432,
                    0.068571426,
                    0.038571432,
                ],
                [
                    0.73417723,
                    0.034177214,
                    0.034177214,
                    0.034177214,
                    0.034177214,
                    0.094936706,
                    0.034177214,
                ],
                [
                    0.73214287,
                    0.03214286,
                    0.03214286,
                    0.057142857,
                    0.03214286,
                    0.057142857,
                    0.057142857,
                ],
                [
                    0.73214287,
                    0.03214286,
                    0.03214286,
                    0.057142857,
                    0.03214286,
                    0.057142857,
                    0.057142857,
                ],
                [
                    0.7623376,
                    0.035064936,
                    0.035064936,
                    0.035064936,
                    0.035064936,
                    0.062337663,
                    0.035064936,
                ],
            ]
            assert np.allclose(jointactionvalues, expected[i])

    def test_fall_roll3_30pct(self):
        game = Game()
        game.set_orders("ITALY", ("F NAP - ION",))
        game.set_orders("RUSSIA", ("A WAR - GAL",))
        game.set_orders("AUSTRIA", ("F TRI - ADR",))
        game.process()
        results = self._test_helper(
            game, max_rollout_length=3, year_spring_prob_of_ending="1902,0.5;1903,0.02"
        )
        for i, (jointaction, jointactionvalues) in enumerate(results):
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)

            # Rollout 3 from fall reaches spring 1903, but only sees tiny differences since 1903
            # ending chance is tiny
            expected = [
                [
                    0.5484416,
                    0.06662338,
                    0.06662338,
                    0.06662338,
                    0.06662338,
                    0.11844156,
                    0.06662338,
                ],
                [
                    0.5465642,
                    0.0665642,
                    0.0665642,
                    0.0665642,
                    0.0665642,
                    0.12061483,
                    0.0665642,
                ],
                [
                    0.54642856,
                    0.06642857,
                    0.068095244,
                    0.06642857,
                    0.068095244,
                    0.11809524,
                    0.06642857,
                ],
                [
                    0.5466234,
                    0.06844156,
                    0.06662338,
                    0.06662338,
                    0.06662338,
                    0.11844156,
                    0.06662338,
                ],
                [
                    0.5483364,
                    0.06833635,
                    0.0665642,
                    0.06529838,
                    0.0665642,
                    0.11833635,
                    0.0665642,
                ],
            ]
            assert np.allclose(jointactionvalues, expected[i])

    def test_fall_roll3_30pctB(self):
        game = Game()
        game.set_orders("ITALY", ("F NAP - ION",))
        game.set_orders("RUSSIA", ("A WAR - GAL",))
        game.set_orders("AUSTRIA", ("F TRI - ADR",))
        game.process()
        results = self._test_helper(
            game, max_rollout_length=3, year_spring_prob_of_ending="1902,0.02;1903,0.5"
        )
        for i, (jointaction, jointactionvalues) in enumerate(results):
            jointactionvalues = [jointactionvalues[power] for power in POWERS]
            print(jointactionvalues)

            # Rollout 3 from fall reaches spring 1903, but sees larger differences since 1903
            # ending chance is large
            expected = [
                [
                    0.58646756,
                    0.061012987,
                    0.061012987,
                    0.061012987,
                    0.061012987,
                    0.108467534,
                    0.061012987,
                ],
                [
                    0.5395335,
                    0.059533454,
                    0.059533454,
                    0.059533454,
                    0.059533454,
                    0.16279927,
                    0.059533454,
                ],
                [
                    0.5361429,
                    0.05614286,
                    0.09780952,
                    0.05614286,
                    0.09780952,
                    0.09980953,
                    0.05614286,
                ],
                [
                    0.541013,
                    0.10646753,
                    0.061012987,
                    0.061012987,
                    0.061012987,
                    0.108467534,
                    0.061012987,
                ],
                [
                    0.5838373,
                    0.10383725,
                    0.059533454,
                    0.027887885,
                    0.059533454,
                    0.105837256,
                    0.059533454,
                ],
            ]
            assert np.allclose(jointactionvalues, expected[i])
