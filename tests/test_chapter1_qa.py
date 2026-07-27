"""Deterministic contracts for the Chapter 1 pacing/performance QA tool."""

from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager, InputSnapshot
from tools.validate_chapter1 import (
    BENCHMARK_LEVEL_ID,
    DEFAULT_DEBRIS_BUDGET,
    DEFAULT_EFFECT_BUDGET,
    FIXED_HZ,
    build_pacing_report,
    build_scene_budget_report,
    run_crowded_benchmark,
    summarize_timing_ns,
)


class ChapterOnePacingReportTests(unittest.TestCase):
    def test_authored_profiles_report_exact_values_without_claiming_observed_time(self) -> None:
        report = build_pacing_report()

        self.assertEqual(
            report["classification"],
            "authored_duration_contract_not_observed_playthrough",
        )
        self.assertIsNone(report["observed_playthrough_seconds"])
        self.assertEqual(report["profiles"]["normal"]["total_minutes"], 53.0)
        self.assertEqual(report["profiles"]["experienced"]["total_minutes"], 36.6)
        self.assertEqual(report["profiles"]["minimum"]["total_minutes"], 35.0)
        self.assertEqual(report["profiles"]["normal"]["travel_dialogue_minutes"], 5.25)
        self.assertEqual(
            report["profiles"]["normal"]["level_minutes"],
            {
                "chapter_1_level_1": 11.25,
                "chapter_1_level_2": 11.5,
                "chapter_1_level_3": 13.25,
                "chapter_1_level_4": 11.75,
            },
        )
        self.assertTrue(report["passed"])
        self.assertTrue(all(report["checks"].values()))
        self.assertTrue(all(report["per_level_normal_checks"].values()))

    def test_four_player_finale_budget_comes_from_content_and_is_repeatable(self) -> None:
        first = build_scene_budget_report()
        second = build_scene_budget_report()

        self.assertEqual(first, second)
        self.assertEqual(first["level_id"], BENCHMARK_LEVEL_ID)
        self.assertEqual(first["player_count"], 4)
        self.assertEqual(first["chief_count"], 1)
        self.assertEqual(first["active_enemy_budget"], 8)
        self.assertEqual(first["active_effect_budget"], DEFAULT_EFFECT_BUDGET)
        self.assertEqual(first["active_debris_budget"], DEFAULT_DEBRIS_BUDGET)
        self.assertEqual(len(first["enemy_kinds"]), 8)
        self.assertEqual(first["enemy_kinds"].count("couch"), 1)
        self.assertEqual(sum(first["enemy_composition"].values()), 8)
        self.assertIn("chapter_content.json", first["enemy_budget_source"])

    def test_budget_overrides_are_bounded_and_labeled_as_tool_arguments(self) -> None:
        report = build_scene_budget_report(effect_budget=7, debris_budget=5)
        self.assertEqual(report["active_effect_budget"], 7)
        self.assertEqual(report["active_debris_budget"], 5)
        self.assertEqual(report["effect_budget_source"], "tool_argument:effect_budget")
        self.assertEqual(report["debris_budget_source"], "tool_argument:debris_budget")
        for kwargs in (
            {"effect_budget": -1},
            {"debris_budget": -1},
            {"effect_budget": 513},
            {"debris_budget": 257},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    build_scene_budget_report(**kwargs)


class ChapterOnePerformanceReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_first_environment_event_advances_without_logging_argument_collision(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [
                SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
            ]
            game._start_stage()
            human = next(player for player in game.players if not player.is_cpu)
            human.x = float(game.meta["stage_width"]) * 0.23
            game._update_stage_content(
                1.0 / FIXED_HZ,
                {human.slot: InputSnapshot()},
            )

            self.assertEqual(game._content_event_index, 1)
            self.assertEqual(len(game._content_event_seen), 1)
        finally:
            game.close()
            manager.close()

    def test_nearest_rank_timing_summary_is_exact_and_rejects_bad_samples(self) -> None:
        samples = (1_000_000, 2_000_000, 3_000_000, 4_000_000, 10_000_000)
        self.assertEqual(
            summarize_timing_ns(samples),
            {
                "mean_ms": 4.0,
                "median_ms": 3.0,
                "p95_ms": 10.0,
                "max_ms": 10.0,
            },
        )
        with self.assertRaises(ValueError):
            summarize_timing_ns(())
        with self.assertRaises(ValueError):
            summarize_timing_ns((1, -1))

    def test_headless_game_workload_holds_every_explicit_budget(self) -> None:
        ticks = iter((
            0,
            1_000_000,
            4_000_000,
            10_000_000,
            12_000_000,
            16_000_000,
        ))
        report = run_crowded_benchmark(
            frames=2,
            warmup_frames=1,
            effect_budget=8,
            debris_budget=6,
            clock_ns=lambda: next(ticks),
        )

        expected = {
            "players": 4,
            "chiefs": 1,
            "active_enemies": 8,
            "active_effects": 8,
            "active_debris": 6,
        }
        self.assertEqual(report["classification"], "deterministic_injected_clock_test_measurement")
        self.assertEqual(report["environment"]["sdl_video_driver"], "dummy")
        self.assertEqual(report["environment"]["timing_clock"], "injected_clock")
        self.assertEqual(report["workload"]["fixed_hz"], FIXED_HZ)
        self.assertEqual(report["workload"]["measured_frames"], 2)
        self.assertEqual(len(report["workload"]["scene_signature_sha256"]), 64)
        self.assertEqual(report["counts"]["expected"], expected)
        self.assertEqual(report["counts"]["initial"], expected)
        self.assertEqual(report["counts"]["minimum"], expected)
        self.assertEqual(report["counts"]["peak"], expected)
        self.assertTrue(report["counts"]["budgets_preserved"])
        self.assertEqual(report["timing"]["update"]["mean_ms"], 1.5)
        self.assertEqual(report["timing"]["draw"]["mean_ms"], 3.5)
        self.assertEqual(report["timing"]["update_plus_draw"]["p95_ms"], 6.0)
        self.assertTrue(report["passed"])
        json.dumps(report, allow_nan=False)

    def test_benchmark_frame_limits_fail_before_constructing_a_game(self) -> None:
        for kwargs in (
            {"frames": 0},
            {"frames": 601},
            {"warmup_frames": -1},
            {"warmup_frames": 181},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    run_crowded_benchmark(**kwargs)


if __name__ == "__main__":
    unittest.main()
