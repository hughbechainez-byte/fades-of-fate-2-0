from __future__ import annotations

from copy import deepcopy
import unittest

from src.chapter_content import (
    ChapterContentError,
    compile_couch_contract,
    compile_level_content,
    level_content,
    load_chapter_content,
    pace_profile,
    validate_chapter_content,
)
from src.config import load_gameplay


class ChapterContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gameplay = load_gameplay()
        self.content = load_chapter_content(gameplay=self.gameplay)

    def test_shipped_content_has_the_canonical_four_level_geographic_route(self) -> None:
        routes = [
            (level["runtime_level_id"], level["route"]["start"], level["route"]["end"])
            for level in self.content["levels"]
        ]
        self.assertEqual(
            routes,
            [
                ("chapter_1_level_1", "Sprouts Parking Lot", "El Cilantro at Madison"),
                ("chapter_1_level_2", "7-Eleven", "I-8 Underpass"),
                ("chapter_1_level_3", "Soapy Joe's", "Revive Pathway"),
                ("chapter_1_level_4", "Awaken Church", "Dave's BMX"),
            ],
        )
        self.assertIn("Madison Plaza", self.content["levels"][1]["route"]["stops"])
        self.assertLess(
            self.content["levels"][1]["route"]["stops"].index("Madison Plaza"),
            self.content["levels"][1]["route"]["stops"].index("I-8 Underpass"),
        )
        bridge = self.content["inter_level_travel"][1]
        self.assertEqual(bridge["heading"], "I-8 TO SOAPY JOE'S")
        bridge_text = " ".join(bridge["beats"]).lower()
        self.assertIn("690", bridge_text)
        self.assertIn("fuel", bridge_text)

    def test_every_level_has_complete_authored_content_and_checkpoints(self) -> None:
        for level in self.content["levels"]:
            with self.subTest(level=level["runtime_level_id"]):
                self.assertGreaterEqual(len(level["major_fights"]), 3)
                self.assertGreaterEqual(len(level["ambush_or_optional"]), 1)
                self.assertGreaterEqual(len(level["environmental_events"]), 1)
                self.assertGreaterEqual(len(level["story_beats"]), 1)
                self.assertGreaterEqual(len(level["landmark_set_pieces"]), 1)
                self.assertGreaterEqual(len(level["traversal_gaps"]), 1)
                self.assertGreaterEqual(len(level["checkpoints"]), 3)
                self.assertTrue(level["ending"]["visual"])
                self.assertTrue(level["ending"]["narrative"])

    def test_compiled_waves_are_deterministic_and_scale_with_player_count(self) -> None:
        solo = compile_level_content(self.content, "chapter_1_level_2", 1)
        four_player = compile_level_content(self.content, "chapter_1_level_2", 4)
        repeat = compile_level_content(self.content, "chapter_1_level_2", 4)

        self.assertEqual(four_player, repeat)
        self.assertEqual(solo["runtime_scaling"]["max_live_enemies"], 5)
        self.assertEqual(four_player["runtime_scaling"]["max_live_enemies"], 8)
        solo_kinds = [
            kind
            for encounter in [*solo["major_fights"], *solo["ambush_or_optional"]]
            for group in encounter["spawn_groups"]
            for kind in group["runtime_kinds"]
        ]
        four_kinds = [
            kind
            for encounter in [*four_player["major_fights"], *four_player["ambush_or_optional"]]
            for group in encounter["spawn_groups"]
            for kind in group["runtime_kinds"]
        ]
        self.assertGreater(len(four_kinds), len(solo_kinds))
        self.assertTrue(set(four_kinds).issubset({"stick", "cart", "whip", "pipe", "security", "homeless", "police", "couch"}))
        source_group = level_content(self.content, "chapter_1_level_2")["major_fights"][0]["spawn_groups"][0]
        self.assertNotIn("runtime_kinds", source_group)
        self.assertNotIn("resolved_variant_ids", source_group)

    def test_pacing_profiles_meet_the_chapter_and_level_targets(self) -> None:
        normal = pace_profile(self.content, "normal")
        experienced = pace_profile(self.content, "experienced")
        minimum = pace_profile(self.content, "minimum")

        self.assertGreaterEqual(normal.total_minutes, 45.0)
        self.assertLessEqual(normal.total_minutes, 60.0)
        self.assertGreaterEqual(experienced.total_minutes, 30.0)
        self.assertLessEqual(experienced.total_minutes, 40.0)
        self.assertGreaterEqual(minimum.total_minutes, 35.0)
        self.assertGreaterEqual(normal.travel_dialogue_minutes, 4.0)
        self.assertLessEqual(normal.travel_dialogue_minutes, 7.0)
        target_ranges = self.content["pacing"]["targets"]["level_target_minutes"]
        for level_id, minutes in normal.level_minutes:
            low, high = target_ranges[level_id]
            self.assertGreaterEqual(minutes, low)
            self.assertLessEqual(minutes, high)

    def test_couch_contract_requires_three_phases_and_two_real_bmx_retreats(self) -> None:
        contract = self.content["couch_boss_contract"]
        self.assertEqual(contract["bike_refuge"]["x"], 1080)
        self.assertEqual([phase["starts_at_health_ratio"] for phase in contract["phases"]], [1.0, 0.67, 0.34])
        retreats = [phase["retreat"] for phase in contract["phases"] if "retreat" in phase]
        self.assertEqual(len(retreats), 2)
        self.assertTrue(all(retreat["destination"] == "daves_bmx" for retreat in retreats))
        self.assertTrue(all(retreat["returns_targetable_after_clear"] for retreat in retreats))
        self.assertTrue(
            all(retreat["taunt"] == "I'LL GIVE YOU DOPE IF YOU BEAT THEM UP!" for retreat in retreats)
        )
        solo = compile_couch_contract(self.content, 1)
        four_player = compile_couch_contract(self.content, 4)
        solo_crew = [
            kind
            for phase in solo["phases"]
            for kind in phase.get("retreat", {}).get("runtime_kinds", ())
        ]
        four_player_crew = [
            kind
            for phase in four_player["phases"]
            for kind in phase.get("retreat", {}).get("runtime_kinds", ())
        ]
        self.assertGreater(len(four_player_crew), len(solo_crew))
        self.assertNotIn("security", four_player_crew)
        self.assertNotIn("couch", four_player_crew)

    def test_validator_rejects_missing_optional_content_and_unknown_enemy_variants(self) -> None:
        missing_optional = deepcopy(self.content)
        missing_optional["levels"][0]["ambush_or_optional"] = []
        with self.assertRaisesRegex(ChapterContentError, "ambush_or_optional"):
            validate_chapter_content(missing_optional)

        unknown_variant = deepcopy(self.content)
        unknown_variant["levels"][1]["major_fights"][0]["spawn_groups"][0]["variants"][0] = "not_a_real_variant"
        with self.assertRaisesRegex(ChapterContentError, "unknown enemy variant"):
            validate_chapter_content(unknown_variant)

    def test_validator_rejects_route_drift_and_bad_couch_phase_shape(self) -> None:
        route_drift = deepcopy(self.content)
        route_drift["levels"][1]["runtime_level_id"] = "chapter_1_level_3"
        with self.assertRaisesRegex(ChapterContentError, "runtime_level_id"):
            validate_chapter_content(route_drift)

        bad_couch = deepcopy(self.content)
        bad_couch["couch_boss_contract"]["phases"].pop()
        with self.assertRaisesRegex(ChapterContentError, "exactly three combat phases"):
            validate_chapter_content(bad_couch)

    def test_compiler_rejects_out_of_range_player_count(self) -> None:
        with self.assertRaisesRegex(ChapterContentError, "between 1 and 4"):
            compile_level_content(self.content, "chapter_1_level_1", 0)
        with self.assertRaisesRegex(ChapterContentError, "between 1 and 4"):
            compile_level_content(self.content, "chapter_1_level_1", 5)


if __name__ == "__main__":
    unittest.main()
