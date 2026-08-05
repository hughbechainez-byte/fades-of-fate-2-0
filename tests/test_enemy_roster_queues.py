from __future__ import annotations

import os
import unittest
from copy import deepcopy

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.config import ConfigError, load_gameplay, validate_gameplay
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


class EnemyRosterQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        self.manager = InputManager(max_players=4, discover_controllers=False)
        self.game = FadesGame(self.manager, mute=True)
        self.game.select_slots = [
            SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
        ]

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def _start_level(self, level_id: str) -> None:
        if self.game.level_id != level_id:
            self.game._select_campaign_level(level_id)
        self.game._start_stage()

    def _begin_named_encounter(self, level_id: str, encounter_name: str) -> None:
        self._start_level(level_id)
        encounter = next(
            encounter
            for encounter in self.game.data["encounters"]
            if encounter["name"] == encounter_name
        )
        self.game._begin_encounter(encounter)

    def test_uncapped_group_resolution_retains_authored_arrival_order(self) -> None:
        self._start_level("chapter_1_level_1")
        fight = self.game._content_major_by_hook["town & country"]

        self.assertEqual(
            self.game._spawn_identifiers_from_groups(fight["spawn_groups"]),
            [
                "road_raider_stick",
                "road_raider_whip",
                "road_raider_cart",
                "road_raider_pipe",
                "mall_security_watch",
                "event_security_heavy",
            ],
        )

    def test_live_main_queues_keep_each_new_security_and_police_role(self) -> None:
        expected_queues = (
            (
                "chapter_1_level_1",
                "Town & Country",
                [
                    "road_raider_stick",
                    "mall_security_watch",
                    "road_raider_whip",
                    "event_security_heavy",
                    "road_raider_cart",
                ],
            ),
            (
                "chapter_1_level_1",
                "El Cilantro at Madison",
                [
                    "road_raider_cart",
                    "night_security_patrol",
                    "road_raider_stick",
                    "road_raider_whip",
                    "road_raider_pipe",
                ],
            ),
            (
                "chapter_1_level_2",
                "7-Eleven Pad",
                [
                    "road_raider_stick",
                    "city_patrol_nightstick",
                    "road_raider_cart",
                    "bike_patrol_taser",
                    "road_raider_whip",
                ],
            ),
            (
                "chapter_1_level_2",
                "I-8 Underpass",
                [
                    "freeway_scout",
                    "transit_patrol_nightstick",
                    "road_raider_cart",
                    "tactical_taser_unit",
                    "road_raider_pipe",
                ],
            ),
            (
                "chapter_1_level_3",
                "Broadway Turn",
                [
                    "road_raider_cart",
                    "night_security_patrol",
                    "road_raider_stick",
                    "riot_line_nightstick",
                    "road_raider_whip",
                ],
            ),
        )

        for level_id, encounter_name, expected in expected_queues:
            with self.subTest(level=level_id, encounter=encounter_name):
                self._begin_named_encounter(level_id, encounter_name)
                self.assertEqual(self.game.spawn_queue, expected)


class PoliceTaserConfigTests(unittest.TestCase):
    def test_police_taser_ranges_must_be_positive(self) -> None:
        gameplay = load_gameplay()
        for field in ("ranged_attack_range", "ranged_depth_range"):
            with self.subTest(field=field):
                invalid = deepcopy(gameplay)
                invalid["enemies"]["police"][field] = 0
                with self.assertRaisesRegex(ConfigError, rf"enemies\.police\.{field}"):
                    validate_gameplay(invalid)


if __name__ == "__main__":
    unittest.main()
