"""Chapter 1 route, boss-placement, and active-level runtime contracts."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.animation_manifest import ANIMATION_CLIPS, total_authored_poses
from src.config import active_campaign_level, load_gameplay
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager, InputSnapshot
from src.world_engine import WorldPoint
import src.sprite_atlas as sprite_atlas


def _translation_normalized_signature(surface: pygame.Surface) -> tuple[tuple[int, int], bytes]:
    bounds = surface.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        raise AssertionError("authored animation pose is empty")
    cropped = surface.subsurface(bounds).copy()
    return cropped.get_size(), pygame.image.tobytes(cropped, "RGBA")


class ChapterOneLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))

    @classmethod
    def tearDownClass(cls) -> None:
        sprite_atlas.clear_cache()
        pygame.quit()

    def setUp(self) -> None:
        self.data = load_gameplay()
        self.chapter = next(
            chapter
            for chapter in self.data["campaign"]["chapters"]
            if chapter["id"] == "chapter_1"
        )
        self.levels = self.chapter["levels"]

    def test_chapter_one_route_uses_the_requested_four_level_order(self) -> None:
        self.assertEqual([level["number"] for level in self.levels], [1, 2, 3, 4])
        self.assertEqual(
            [(level["start"]["id"], level["end"]["id"]) for level in self.levels],
            [
                ("sprouts_parking_lot", "el_cilantro_madison"),
                ("seven_eleven", "i8_underpass"),
                ("soapy_joes", "revive_pathway"),
                ("awaken_church_lot", "daves_bmx"),
            ],
        )
        self.assertEqual(self.data["campaign"]["active_level_id"], self.levels[0]["id"])
        self.assertEqual([level["status"] for level in self.levels], ["playable"] * 4)
        self.assertEqual(
            [level["background_theme"] for level in self.levels],
            [
                "sprouts_el_cilantro",
                "seven_eleven_underpass",
                "soapy_joes_revive",
                "awaken_church_finale",
            ],
        )
        for level in self.levels:
            self.assertEqual(level["stage_geometry"]["rails"][0]["start_x"], 0)
            self.assertEqual(level["stage_geometry"]["rails"][-1]["end_x"], level["stage_width"])

    def test_couch_exists_once_and_only_in_the_awaken_chapter_finale(self) -> None:
        couch_locations: list[tuple[int, int]] = []
        for level in self.levels:
            for encounter_index, encounter in enumerate(level["encounters"]):
                couch_locations.extend(
                    (level["number"], encounter_index)
                    for kind in encounter["base"]
                    if kind == "couch"
                )

        self.assertEqual(couch_locations, [(4, len(self.levels[-1]["encounters"]) - 1)])
        for level in self.levels[:-1]:
            self.assertIsNone(level["boss"])
            self.assertFalse(level["chapter_finale"])
            self.assertFalse(level["boss_transition"])

        finale = self.levels[-1]
        self.assertEqual(finale["boss"], "couch")
        self.assertTrue(finale["chapter_finale"])
        self.assertTrue(finale["boss_transition"])
        self.assertEqual(finale["encounters"][-1]["base"], ["couch"])
        self.assertEqual(finale["start"]["real_name"], "Awaken Church")
        self.assertEqual(finale["start"]["address"], "950 N 2nd St")
        self.assertEqual(finale["end"]["real_name"], "Dave's BMX")

    def test_active_level_one_runtime_data_has_no_couch_or_boss_transition(self) -> None:
        active = active_campaign_level(self.data)
        self.assertEqual(active["id"], "chapter_1_level_1")
        self.assertEqual(active["outro"], "jerry_warning")
        self.assertEqual(self.data["encounters"], active["encounters"])
        self.assertFalse(active["boss_transition"])
        self.assertFalse(self.data["transitions"]["boss_loading"]["enabled"])
        self.assertNotIn(
            "couch",
            [kind for encounter in self.data["encounters"] for kind in encounter["base"]],
        )

    def test_security_reinforcements_escalate_before_the_couch_finale(self) -> None:
        """Guards are post-clear mini-waves, increasingly common through Levels 1-3."""

        def reinforcements(encounter: dict[str, object]) -> list[dict[str, object]]:
            return list(encounter.get("post_clear_reinforcements", ()))

        def encounter_population(level: dict[str, object]) -> int:
            return sum(
                len(encounter["base"])
                + sum(len(reinforcement["base"]) for reinforcement in reinforcements(encounter))
                for encounter in level["encounters"]
            )

        def security_population(level: dict[str, object]) -> int:
            return sum(
                sum(
                    kind == "security"
                    for reinforcement in reinforcements(encounter)
                    for kind in reinforcement["base"]
                )
                for encounter in level["encounters"]
            )

        regular_levels = self.levels[:3]
        populations = [encounter_population(level) for level in regular_levels]
        security_counts = [security_population(level) for level in regular_levels]
        bubbles = [
            str(reinforcement["speech"])
            for level in regular_levels
            for encounter in level["encounters"]
            for reinforcement in reinforcements(encounter)
        ]
        security = self.data["enemies"]["security"]

        self.assertGreater(security["health"], self.data["enemies"]["cart"]["health"])
        self.assertGreater(security["damage"], self.data["enemies"]["cart"]["damage"])
        self.assertEqual(populations, sorted(populations))
        self.assertEqual(security_counts, sorted(security_counts))
        self.assertGreater(security_counts[0], 0)
        self.assertEqual(len(bubbles), len(set(bubbles)))
        self.assertTrue(all("security" not in encounter["base"] for encounter in regular_levels[0]["encounters"]))

        finale = self.levels[-1]
        finale_kinds = [
            kind
            for encounter in finale["encounters"]
            for kind in encounter["base"]
        ]
        finale_kinds.extend(
            kind
            for encounter in finale["encounters"]
            for reinforcement in reinforcements(encounter)
            for kind in reinforcement["base"]
        )
        self.assertNotIn("security", finale_kinds)
        self.assertNotIn("post_clear_reinforcements", finale["encounters"][-1])

    def test_security_arrives_only_after_base_wave_clears_with_a_comic_bubble(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
            game._start_stage()
            encounter = game.data["encounters"][1]
            reinforcement = encounter["post_clear_reinforcements"][0]
            game.encounter_index = 1
            game._begin_encounter(encounter)
            base_gate = game.active_gate

            # The base crowd must be fully gone before the guard queue is
            # promoted; the encounter index and camera gate stay put.
            game.spawn_queue.clear()
            game.enemies.clear()
            game._update_encounters(0.0)
            self.assertTrue(game.encounter_active)
            self.assertEqual(game.encounter_index, 1)
            self.assertEqual(game.active_gate, base_gate)
            self.assertEqual(game.spawn_queue, reinforcement["base"])

            game._update_encounters(0.0)
            guard = next(enemy for enemy in game.enemies if enemy.kind == "security")
            self.assertEqual(game._security_speech_by_enemy[guard.enemy_id][0], reinforcement["speech"])
            surface = pygame.Surface((640, 360), pygame.SRCALPHA)
            with patch("src.game.pixel_art.draw_comic_speech_bubble") as bubble:
                game._draw_gameplay(surface)
            bubble.assert_called_once()

            game.spawn_queue.clear()
            game.enemies.clear()
            game._update_encounters(0.0)
            self.assertFalse(game.encounter_active)
            self.assertEqual(game.encounter_index, 2)
        finally:
            game.close()
            manager.close()

    def test_level_one_landmarks_run_from_sprouts_lot_to_goodwill_and_el_cilantro(self) -> None:
        landmark_ids = [landmark["id"] for landmark in self.levels[0]["landmarks"]]
        self.assertEqual(
            landmark_ids,
            [
                "sprouts_parking_lot",
                "wells_fargo_pad",
                "walmart_neighborhood_market",
                "town_country",
                "goodwill_frontage",
                "madison_intersection",
                "el_cilantro_madison",
            ],
        )
        self.assertEqual(self.levels[0]["end"]["real_name"], "El Cilantro")
        self.assertLess(
            landmark_ids.index("goodwill_frontage"),
            landmark_ids.index("madison_intersection"),
        )
        self.assertLess(
            landmark_ids.index("madison_intersection"),
            landmark_ids.index("el_cilantro_madison"),
        )

    def test_clearing_level_one_final_wave_completes_without_boss_handoff(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [
                SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
            ]
            game._start_stage()
            game.encounter_index = len(game.data["encounters"]) - 1
            game.encounter_active = True
            game.spawn_queue.clear()
            game.enemies.clear()

            game._update_encounters(0.0)

            self.assertIsNone(game.boss_transition)
            self.assertEqual(game.encounter_index, len(game.data["encounters"]))
            self.assertEqual(game.state, "gameplay")
            self.assertIsNotNone(game.level_outro)
            # Completion is still available as an explicit player skip, but
            # elapsed time alone may not silently leave Jerry's dialogue.
            game._update_level_outro(0.0, [InputSnapshot(pressed={"dodge"})])
            self.assertEqual(game.state, "complete")
            self.assertIsNotNone(game.completion_stats)
        finally:
            game.close()
            manager.close()

    def test_level_one_final_wave_does_not_render_couch_bmx_story_prop(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [
                SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
            ]
            game._start_stage()
            game.encounter_index = len(game.data["encounters"]) - 1
            surface = pygame.Surface((640, 360), pygame.SRCALPHA)

            with (
                patch("src.game.pixel_art.draw_stage_background"),
                patch("src.game.pixel_art.draw_bmx_bike") as draw_bmx,
            ):
                game._draw_gameplay(surface)

            draw_bmx.assert_not_called()
        finally:
            game.close()
            manager.close()

    def test_content_props_render_as_dicts_without_actor_attribute_access(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
            game._start_stage()
            game._content_event_props = [
                {
                    "id": "test_tent",
                    "depth": 280.0,
                    "x": 240.0,
                    "y": 300.0,
                    "kind": "tent_camp",
                    "smoke_phase": 0.25,
                }
            ]
            surface = pygame.Surface((640, 360), pygame.SRCALPHA)

            with patch("src.game.pixel_art.draw_tent_camp") as draw_tent_camp:
                game._draw_gameplay(surface)

            draw_tent_camp.assert_called_once()
        finally:
            game.close()
            manager.close()

    def test_collision_props_and_near_occluders_render_in_depth_order(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
            for level in self.levels:
                with self.subTest(level=level["id"]):
                    game._select_campaign_level(str(level["id"]))
                    game._start_stage()
                    obstacles = game.data["stage_geometry"]["obstacles"]
                    for obstacle in obstacles:
                        self.assertFalse(
                            game.stage_geometry.is_walkable(WorldPoint(float(obstacle["x"]), float(obstacle["depth"]))),
                            f"{obstacle['id']} must share its visible prop record with collision geometry",
                        )

                    order: list[str] = []
                    surface = pygame.Surface((640, 360), pygame.SRCALPHA)
                    with (
                        patch("src.game.pixel_art.draw_stage_background", side_effect=lambda *args, **kwargs: order.append("background") or surface.get_rect()),
                        patch("src.game.pixel_art.draw_stage_prop", side_effect=lambda *args, **kwargs: order.append("prop") or pygame.Rect(0, 0, 1, 1)) as draw_prop,
                        patch("src.game.pixel_art.draw_stage_foreground", side_effect=lambda *args, **kwargs: order.append("foreground") or surface.get_rect()) as draw_foreground,
                    ):
                        game._draw_gameplay(surface)

                    self.assertEqual(draw_prop.call_count, len(obstacles))
                    draw_foreground.assert_called_once()
                    self.assertEqual(order[0], "background")
                    self.assertEqual(order[-1], "foreground")
                    self.assertTrue(all(entry == "prop" for entry in order[1:-1]))
        finally:
            game.close()
            manager.close()

    @staticmethod
    def _start_level(game: FadesGame, level_id: str) -> None:
        game._select_campaign_level(level_id)
        game._start_stage()

    @staticmethod
    def _clear_regular_encounters(game: FadesGame) -> None:
        """Travel through every non-boss trigger and resolve its full wave."""

        human = next(player for player in game.players if not player.is_cpu)
        while game.encounter_index < len(game.data["encounters"]):
            encounter = game.data["encounters"][game.encounter_index]
            if encounter["base"] == ["couch"]:
                return
            human.x = float(encounter["trigger_x"])
            game._update_encounters(0.0)
            assert game.encounter_active
            game.spawn_queue.clear()
            game.enemies.clear()
            game._update_encounters(0.0)

    def test_level_one_to_three_each_run_every_authored_encounter_and_advance_in_order(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [
                SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
            ]
            for expected_level in self.levels[:3]:
                with self.subTest(level=expected_level["number"]):
                    self._start_level(game, expected_level["id"])
                    self.assertEqual(game.level_theme, expected_level["background_theme"])
                    self.assertEqual(game.meta["stage_width"], expected_level["stage_width"])
                    self.assertEqual(game.data["stage_geometry"], expected_level["stage_geometry"])
                    self._clear_regular_encounters(game)
                    if expected_level.get("outro") == "jerry_warning":
                        self.assertIsNotNone(game.level_outro)
                        game._update_level_outro(0.0, [InputSnapshot(pressed={"dodge"})])
                    self.assertEqual(game.state, "complete")
                    self.assertTrue(game.level_stats.finished)

                    # The player-owned roster stays intact while the next
                    # level is loaded through the on-screen route card.
                    if expected_level["number"] < 3:
                        game._open_epilogue()
                        game.epilogue_selection = 0
                        game._activate_epilogue_selection()
                        self.assertEqual(game.state, "interlevel")
                        self.assertEqual(game.pending_level_id, self.levels[expected_level["number"]]["id"])
                        game._start_pending_level(source="test")
                        self.assertEqual(game.state, "gameplay")
                        self.assertEqual(game.level_id, self.levels[expected_level["number"]]["id"])
            self.assertEqual(game.level_id, self.levels[2]["id"])
        finally:
            game.close()
            manager.close()

    def test_interlevel_runtime_uses_manifest_route_card_and_both_moving_panels(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            transitions = (
                (self.levels[0], self.levels[1], "route_card"),
                (self.levels[1], self.levels[2], "moving_panel"),
                (self.levels[2], self.levels[3], "moving_panel"),
            )
            for source, destination, presentation in transitions:
                with self.subTest(source=source["id"], destination=destination["id"]):
                    game._select_campaign_level(str(source["id"]))
                    game._begin_interlevel(destination)
                    panel = game.interlevel_travel_panel
                    self.assertIsNotNone(panel)
                    assert panel is not None
                    self.assertEqual(panel["presentation"], presentation)
                    self.assertEqual(
                        game.interlevel_duration,
                        3.8 if presentation == "moving_panel" else 1.75,
                    )
                    game.interlevel_timer = game.interlevel_duration * 0.5
                    canvas = pygame.Surface((640, 360))
                    with (
                        patch("src.game.pixel_art.draw_location_travel_panel") as moving,
                        patch("src.game.pixel_art.draw_stage_background") as route_card,
                    ):
                        game._draw_interlevel(canvas)
                    if presentation == "moving_panel":
                        moving.assert_called_once()
                        self.assertEqual(moving.call_args.args[1]["id"], panel["id"])
                        self.assertAlmostEqual(moving.call_args.args[2], 0.5)
                        route_card.assert_not_called()
                    else:
                        moving.assert_not_called()
                        route_card.assert_called_once()
        finally:
            game.close()
            manager.close()

    def test_level_four_couch_handoff_uses_finale_geometry_and_completes(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [
                SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
            ]
            finale = self.levels[-1]
            self._start_level(game, finale["id"])
            self.assertTrue(game.level_has_couch)
            self.assertTrue(game.level_is_chapter_finale)
            self.assertEqual(game.meta["stage_width"], 1600)
            self.assertTrue(game.data["transitions"]["boss_loading"]["enabled"])
            self.assertEqual(game.data["transitions"]["boss_loading"]["party_x"], 1120)

            # Clear Revive Front Lot through the normal trigger/gate path.
            self._clear_regular_encounters(game)
            transition = game.boss_transition
            self.assertIsNotNone(transition)
            assert transition is not None
            self.assertEqual(game.encounter_index, 1)
            game._update_boss_transition(transition.relocate_seconds)
            self.assertGreater(min(player.x for player in game.players), 1000.0)
            game._update_boss_transition(transition.duration_seconds - transition.relocate_seconds)
            self.assertTrue(game.encounter_active)
            self.assertEqual(game.spawn_queue, ["couch"])

            game._update_encounters(0.0)
            boss = next(enemy for enemy in game.enemies if enemy.kind == "couch")
            boss.update(game, boss.state_duration)
            human = next(player for player in game.players if not player.is_cpu)
            for _ in range(2):
                self.assertTrue(boss.take_damage(100_000, game, human, knockdown=True))
                boss.update(game, 20.0)
                retreat = game.couch_retreat
                self.assertIsNotNone(retreat)
                assert retreat is not None
                for add in game.enemies:
                    if add.enemy_id in retreat.add_enemy_ids:
                        add._set_state("chase")
                        add.take_damage(100_000, game, human)
                boss.update(game, float(boss.stats["retreat_minimum_refuge_seconds"]))
                boss.update(game, 20.0)
            self.assertTrue(boss.take_damage(100_000, game, human, knockdown=True))
            game._update_encounters(0.0)
            self.assertEqual(game.state, "complete")
            self.assertTrue(game.level_stats.finished)
            self.assertIsNotNone(game.completion_stats)
        finally:
            game.close()
            manager.close()

    def test_animation_floor_remains_above_five_meaningful_poses(self) -> None:
        self.assertGreaterEqual(total_authored_poses(), 600)
        for clip in ANIMATION_CLIPS:
            with self.subTest(actor=clip.actor, state=clip.state):
                poses = sprite_atlas.animation_frames(clip.actor, clip.state)
                self.assertGreaterEqual(len(poses), 5)
                self.assertGreaterEqual(len(set(clip.phases)), 5)
                meaningful = {_translation_normalized_signature(pose) for pose in poses}
                self.assertGreaterEqual(
                    len(meaningful),
                    5,
                    "animation uses repeated or translation-only filler",
                )


if __name__ == "__main__":
    unittest.main()
