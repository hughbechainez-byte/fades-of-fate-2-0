from __future__ import annotations

import os
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest import mock


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.atmosphere import AtmosphereSnapshot, AtmosphereState
from src.config import campaign_levels, load_gameplay, resource_path
from src.game import FadesGame
from src.input_manager import InputManager
from src.level_complete import CompletionStats
from src.location_lock import load_location_lock
from src.progression import (
    DEFAULT_FIRST_LEVEL_ID,
    GameOptions,
    LoadResult,
    SaveData,
)


class _BackgroundCaptured(RuntimeError):
    pass


class _SnapshotProbe:
    def __init__(self, state: AtmosphereState) -> None:
        self.state = state
        self.calls = 0
        self.result = state.snapshot()

    def snapshot(self) -> AtmosphereSnapshot:
        self.calls += 1
        return self.result


class GameAtmosphereIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    @staticmethod
    def _bare_update_game(state: str, *, paused: bool = False) -> FadesGame:
        game = object.__new__(FadesGame)
        game.elapsed = 0.0
        game.frame = 0
        game.controller_notice = 0.0
        game.state = state
        game.pause = paused
        game.atmosphere = AtmosphereState.new(seed=2026)
        game.input = SimpleNamespace(controller_count=0)
        game._last_controller_count = 0
        game.loading_timer = 100.0
        game.complete_timer = 0.0
        game.epilogue_timer = 0.0
        game.level_is_chapter_finale = False
        game.victory_frame = SimpleNamespace(show_results=False)
        game.select_slots = []
        game._update_gameplay = mock.Mock()
        game._update_pause_menu = mock.Mock()
        game._update_character_select = mock.Mock()
        game._update_epilogue = mock.Mock()
        game._update_interlevel = mock.Mock()
        game.log_breadcrumb = mock.Mock()
        return game

    def test_constructor_detaches_atmosphere_and_resolves_projection_profile(self) -> None:
        loaded_atmosphere = AtmosphereState.new(seed=7331)
        loaded_atmosphere.advance(0.75)
        loaded_save = SaveData(atmosphere=loaded_atmosphere)
        before = loaded_atmosphere.to_mapping()
        manager = InputManager(max_players=4, discover_controllers=False)

        with mock.patch(
            "src.game.SaveRepository.load",
            return_value=LoadResult(data=loaded_save, status="loaded"),
        ):
            game = FadesGame(manager, mute=True)

        try:
            self.assertIs(game.save_data, loaded_save)
            self.assertIsNot(game.atmosphere, loaded_atmosphere)
            self.assertEqual(game.atmosphere.to_mapping(), before)
            self.assertEqual(game._projection_profile_id, "chapter1_oblique_v2")
            self.assertEqual(game.projection.config.mode, "oblique_orthographic")
            self.assertAlmostEqual(game.projection.config.oblique_x_per_depth, 0.07)

            game.atmosphere.advance(0.25)
            self.assertEqual(loaded_atmosphere.to_mapping(), before)
            self.assertGreater(game.atmosphere.time_seconds, loaded_atmosphere.time_seconds)
        finally:
            game.close()
            manager.close()

    def test_mute_game_uses_default_options_not_host_saved_options(self) -> None:
        loaded_save = SaveData(
            options=GameOptions(super_attack_characters=("black_dave",)),
        )
        manager = InputManager(max_players=4, discover_controllers=False)

        with mock.patch(
            "src.game.SaveRepository.load",
            return_value=LoadResult(data=loaded_save, status="loaded"),
        ):
            game = FadesGame(manager, mute=True)

        try:
            self.assertEqual(game.save_data.options.super_attack_characters, ("black_dave",))
            self.assertEqual(game.options, GameOptions())
            self.assertTrue(game._is_super_attack_enabled("shelly"))
        finally:
            game.close()
            manager.close()

    def test_update_advances_only_presentation_states_and_freezes_pause(self) -> None:
        for state in ("gameplay", "complete", "interlevel", "epilogue"):
            with self.subTest(state=state):
                game = self._bare_update_game(state)
                before = game.atmosphere.snapshot()
                game.update(0.04)
                self.assertAlmostEqual(game.atmosphere.time_seconds, before.time_seconds + 0.04)
                self.assertNotEqual(game.atmosphere.cloud_phases, before.cloud_phases)

        paused = self._bare_update_game("gameplay", paused=True)
        paused_before = paused.atmosphere.snapshot()
        paused.update(0.04)
        self.assertEqual(paused.atmosphere.snapshot(), paused_before)

        for state in ("loading", "title", "character_select", "game_over"):
            with self.subTest(non_presentation_state=state):
                game = self._bare_update_game(state)
                before = game.atmosphere.snapshot()
                game.update(0.04)
                self.assertEqual(game.atmosphere.snapshot(), before)

    def test_route_selection_targets_profile_without_resetting_clock_or_seed(self) -> None:
        game = object.__new__(FadesGame)
        game.data = load_gameplay()
        manifest_path = resource_path("data/chapter1_location_lock.json")
        game.location_manifest_path = manifest_path
        game.location_manifest = load_location_lock(
            manifest_path,
            project_root=manifest_path.parent.parent,
        )
        game.atmosphere = AtmosphereState.new(seed=404)
        game.atmosphere.advance(1.25)
        game._validate_location_route_binding = mock.Mock()
        game.log_breadcrumb = mock.Mock()
        original_seed = game.atmosphere.seed
        original_time = game.atmosphere.time_seconds
        expected_profiles = {
            "chapter_1_level_1": "chapter_1_sunset",
            "chapter_1_level_2": "i8_underpass_dimming",
            "chapter_1_level_3": "broadway_blue_hour",
            "chapter_1_level_4": "awaken_finale",
            "chapter_2_level_1": "chapter_2_neon_dusk_bostonia",
            "chapter_2_level_2": "chapter_2_neon_dusk_underpass",
            "chapter_2_level_3": "chapter_2_neon_dusk_promenade",
            "chapter_2_level_4": "chapter_2_neon_dusk_boss",
        }

        for level in campaign_levels(game.data):
            level_id = str(level["id"])
            with self.subTest(level_id=level_id):
                game._select_campaign_level(level_id)
                self.assertEqual(
                    game.atmosphere.target_profile_id,
                    expected_profiles[level_id],
                )
                self.assertEqual(game.atmosphere.seed, original_seed)
                self.assertEqual(game.atmosphere.time_seconds, original_time)

    def test_interlevel_begins_destination_palette_without_restart_at_stage_start(self) -> None:
        game = object.__new__(FadesGame)
        game.data = load_gameplay()
        manifest_path = resource_path("data/chapter1_location_lock.json")
        game.location_manifest_path = manifest_path
        game.location_manifest = load_location_lock(
            manifest_path,
            project_root=manifest_path.parent.parent,
        )
        game.level_id = DEFAULT_FIRST_LEVEL_ID
        game.atmosphere = AtmosphereState.new(
            seed=404,
            profile_id="chapter_1_sunset",
        )
        game.audio = mock.Mock()
        game.log_breadcrumb = mock.Mock()
        next_level = campaign_levels(game.data)[1]

        game._begin_interlevel(next_level)
        self.assertEqual(
            game.atmosphere.target_profile_id,
            "i8_underpass_dimming",
        )
        game.atmosphere.advance(0.75)
        progress_during_travel = game.atmosphere.transition_progress
        self.assertGreater(progress_during_travel, 0.0)

        game._validate_location_route_binding = mock.Mock()
        game._select_campaign_level(str(next_level["id"]))

        self.assertEqual(
            game.atmosphere.transition_progress,
            progress_during_travel,
        )

    def test_cancelled_interlevel_restores_source_palette_target(self) -> None:
        game = object.__new__(FadesGame)
        game.level_id = DEFAULT_FIRST_LEVEL_ID
        game.interlevel_source_id = DEFAULT_FIRST_LEVEL_ID
        game.pending_level_id = "chapter_1_level_2"
        game.interlevel_travel_panel = {"id": "test"}
        game.interlevel_timer = 1.0
        game.atmosphere = AtmosphereState.new(
            seed=404,
            profile_id="chapter_1_sunset",
        )
        game.atmosphere.set_profile_for_route("chapter_1_level_2")
        game.atmosphere.advance(0.5)
        game._active_menu_snapshots = mock.Mock(
            return_value=[SimpleNamespace(pressed={"back"})],
        )
        game.audio = mock.Mock()
        game.log_breadcrumb = mock.Mock()

        game._update_interlevel(0.04)

        self.assertEqual(game.state, "epilogue")
        self.assertEqual(
            game.atmosphere.target_profile_id,
            "chapter_1_sunset",
        )

    def test_route_background_draws_receive_one_immutable_snapshot(self) -> None:
        surface = pygame.Surface((640, 360))

        def base_game() -> tuple[FadesGame, _SnapshotProbe]:
            game = object.__new__(FadesGame)
            probe = _SnapshotProbe(AtmosphereState.new(seed=91))
            game.atmosphere = probe
            game.meta = {"stage_width": 4200}
            game.level_theme = "chapter1_el_cilantro"
            game._render_camera_x = 240.0
            game._camera_shake_y = 0.0
            game.data = load_gameplay()
            return game, probe

        scenarios: list[tuple[str, object, FadesGame, _SnapshotProbe]] = []

        gameplay, gameplay_probe = base_game()
        scenarios.append(("gameplay", gameplay._draw_gameplay, gameplay, gameplay_probe))

        complete, complete_probe = base_game()
        scenarios.append(("complete", complete._draw_level_complete, complete, complete_probe))

        interlevel, interlevel_probe = base_game()
        interlevel.pending_level_id = "chapter_1_level_2"
        interlevel.interlevel_source_id = "chapter_1_level_1"
        interlevel.interlevel_travel_panel = {"presentation": "route_card"}
        interlevel.interlevel_timer = 1.0
        interlevel.interlevel_duration = 2.0
        scenarios.append(
            ("interlevel", interlevel._draw_interlevel, interlevel, interlevel_probe)
        )

        epilogue, epilogue_probe = base_game()
        epilogue.level_is_chapter_finale = False
        scenarios.append(("epilogue", epilogue._draw_epilogue, epilogue, epilogue_probe))

        for state, draw_method, _game, probe in scenarios:
            with self.subTest(state=state):
                with mock.patch(
                    "src.game.pixel_art.draw_stage_background",
                    side_effect=_BackgroundCaptured,
                ) as draw_background:
                    with self.assertRaises(_BackgroundCaptured):
                        draw_method(surface)

                self.assertEqual(probe.calls, 1)
                passed = draw_background.call_args.kwargs.get("atmosphere")
                self.assertIs(passed, probe.result)
                self.assertIsInstance(passed, AtmosphereSnapshot)
                with self.assertRaises(FrozenInstanceError):
                    passed.time_seconds = 999.0

    def test_completion_persists_a_detached_atmosphere_snapshot(self) -> None:
        game = object.__new__(FadesGame)
        original_atmosphere = AtmosphereState.new(seed=17)
        original_save = SaveData(atmosphere=original_atmosphere)
        original_mapping = original_atmosphere.to_mapping()
        live = AtmosphereState.from_mapping(original_mapping)
        live.advance(1.5)
        game.save_data = original_save
        game.atmosphere = live
        game.options = GameOptions()
        game.level_id = DEFAULT_FIRST_LEVEL_ID
        game.completion_stats = CompletionStats(
            completion_seconds=84.25,
            combined_score=4200,
            kos=11,
            hits_landed=76,
            damage_taken=18.5,
            rating_points=6100,
            rank="A",
        )
        game._next_campaign_level = mock.Mock(return_value=None)
        game.persistence_enabled = True
        game.save_repository = mock.Mock()
        game.log_breadcrumb = mock.Mock()

        game._persist_completed_level()

        game.save_repository.save.assert_called_once_with(game.save_data)
        self.assertIs(original_save.atmosphere, original_atmosphere)
        self.assertEqual(original_atmosphere.to_mapping(), original_mapping)
        self.assertIsNot(game.save_data, original_save)
        self.assertIsNot(game.save_data.atmosphere, live)
        self.assertEqual(game.save_data.atmosphere.to_mapping(), live.to_mapping())
        with self.assertRaises(FrozenInstanceError):
            game.save_data.atmosphere = live

        saved_mapping = game.save_data.atmosphere.to_mapping()
        live.advance(0.5)
        self.assertEqual(game.save_data.atmosphere.to_mapping(), saved_mapping)


if __name__ == "__main__":
    unittest.main()
