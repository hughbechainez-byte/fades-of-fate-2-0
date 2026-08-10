from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.entities import Enemy, KOCompanion
from src.config import campaign_levels, resource_path
from src.game import (
    FadesGame,
    SOLO_CPU_COMPANIONS,
    SelectSlot,
    _build_title_foreground_cast,
    _title_walker_horizontal_pose,
)
from src.input_manager import InputManager, InputSnapshot
from src.world_engine import WorldPoint


class StateFlowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    @staticmethod
    def _dispatch(game: FadesGame, manager: InputManager, event: pygame.event.Event) -> None:
        manager.process_events([event])
        game.handle_events([event])
        game.update(1.0 / 60.0)
        manager.consume_pressed()

    @classmethod
    def _tap_key(cls, game: FadesGame, manager: InputManager, key: int) -> None:
        cls._dispatch(game, manager, pygame.event.Event(pygame.KEYDOWN, {"key": key}))
        cls._dispatch(game, manager, pygame.event.Event(pygame.KEYUP, {"key": key}))

    @classmethod
    def _tap_controller(
        cls,
        game: FadesGame,
        manager: InputManager,
        instance_id: int,
        button: int,
    ) -> None:
        cls._dispatch(
            game,
            manager,
            pygame.event.Event(
                pygame.CONTROLLERBUTTONDOWN,
                {"instance_id": instance_id, "button": button},
            ),
        )
        cls._dispatch(
            game,
            manager,
            pygame.event.Event(
                pygame.CONTROLLERBUTTONUP,
                {"instance_id": instance_id, "button": button},
            ),
        )

    def test_launch_loading_state_has_only_a_brief_transition(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        self.assertEqual(game.state, "loading")
        self.assertEqual(game.loading_timer, 0.0)
        game.update(1.0 / 60.0)
        self.assertEqual(game.state, "title")

    def test_title_walkers_cross_the_full_street_and_reverse(self) -> None:
        left = _title_walker_horizontal_pose(0.0, left=-48, right=688, period=10.0, phase=0.0)
        right = _title_walker_horizontal_pose(10.0, left=-48, right=688, period=10.0, phase=0.0)
        returning = _title_walker_horizontal_pose(15.0, left=-48, right=688, period=10.0, phase=0.0)
        self.assertEqual(left, (-48, 1))
        self.assertEqual(right, (688, 1))
        self.assertEqual(returning, (320, -1))

    def test_title_foreground_cast_keeps_heroes_opaque_only(self) -> None:
        key_art = pygame.Surface((640, 360))
        key_art.fill((80, 120, 160))
        foreground = _build_title_foreground_cast(key_art)
        self.assertEqual(foreground.get_at((270, 180)).a, 255)
        self.assertEqual(foreground.get_at((345, 180)).a, 255)
        self.assertEqual(foreground.get_at((440, 250)).a, 255)
        self.assertEqual(foreground.get_at((490, 205)).a, 0)
        self.assertEqual(foreground.get_at((100, 180)).a, 0)

    def test_character_select_uses_dedicated_hero_portraits(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        portrait_paths = {
            "black_dave": "assets/portraits/dave_portrait_lean_young_v2.png",
            "shelly": "assets/portraits/shelly_portrait_curvy_v1.png",
            "jermaine": "assets/portraits/jermaine_portrait_pixel_v1.png",
            "white_dave": "assets/portraits/white_dave_portrait_pixel_v2.png",
            "ko": "assets/portraits/ko_portrait_v1.png",
        }
        try:
            for character, relative in portrait_paths.items():
                with self.subTest(character=character):
                    path = Path(resource_path(relative))
                    self.assertTrue(path.is_file())
                    authored = pygame.image.load(str(path)).convert()
                    portrait_sizes = {
                        "black_dave": (90, 145),
                        "shelly": (90, 145),
            "jermaine": (90, 145),
            "white_dave": (90, 145),
                        "ko": (90, 145),
                    }
                    target_width, target_height = portrait_sizes[character]
                    crop_width = min(authored.get_width(), round(authored.get_height() * target_width / target_height))
                    crop_left = max(0, (authored.get_width() - crop_width) // 2)
                    expected = pygame.transform.smoothscale(
                        authored.subsurface(pygame.Rect(crop_left, 0, crop_width, authored.get_height())).copy(),
                        portrait_sizes[character],
                    )
                    self.assertEqual(game.character_portraits[character].get_size(), portrait_sizes[character])
                    self.assertEqual(
                        pygame.image.tobytes(game.character_portraits[character], "RGBA"),
                        pygame.image.tobytes(expected, "RGBA"),
                    )
        finally:
            game.close()
            manager.close()

    def test_ko_portrait_load_failure_never_falls_back_to_placeholder_art(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        original_load = pygame.image.load

        def load_without_ko(path: str) -> pygame.Surface:
            if str(path).replace("\\", "/").endswith("assets/portraits/ko_portrait_v1.png"):
                raise pygame.error("corrupt KO portrait")
            return original_load(path)

        try:
            with mock.patch("src.game.pygame.image.load", side_effect=load_without_ko):
                with self.assertRaisesRegex(RuntimeError, "KO character-select portrait could not be loaded"):
                    FadesGame(manager, mute=True)
        finally:
            manager.close()

    def test_game_selects_configured_menu_stage_and_return_music(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        with mock.patch("src.game.AudioManager") as audio_manager_type:
            audio_manager = audio_manager_type.return_value
            audio_manager.play_music_file.return_value = True
            game = FadesGame(manager, mute=False)
            try:
                menu_music = game.data["audio"]["menu_music"]
                stage_music = game.data["audio"]["stage_music"]
                self.assertEqual(
                    audio_manager.play_music_file.call_args_list,
                    [mock.call(menu_music, loop=True)],
                )

                game.select_slots = [
                    SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
                ]
                game._start_stage()
                self.assertEqual(game.state, "gameplay")
                self.assertEqual(
                    audio_manager.play_music_file.call_args_list[-1],
                    mock.call(stage_music, loop=True),
                )

                game._finish_level(after_outro=True)
                self.assertEqual(game.state, "complete")
                self.assertFalse(game.music_started)
                audio_manager.stop_music.assert_any_call(850)

                game._go_title()
                self.assertEqual(game.state, "title")
                self.assertTrue(game.music_started)
                self.assertEqual(
                    audio_manager.play_music_file.call_args_list[-1],
                    mock.call(menu_music, loop=True),
                )
                self.assertNotEqual(menu_music, stage_music)
            finally:
                game.close()
                manager.close()

    def test_keyboard_solo_selection_owns_dave_with_cpu_shelly_and_shared_chief(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.state = "title"
            self._tap_key(game, manager, pygame.K_SPACE)
            self.assertEqual(game.state, "character_select")
            self.assertTrue(game.select_slots[0].confirmed)
            self.assertEqual(
                game._selection_footer_lines()[0],
                "YOU CONTROL: BLACK DAVE  •  CPU COMPANION: SHELLY",
            )

            self._tap_key(game, manager, pygame.K_SPACE)
            human = next(player for player in game.players if not player.is_cpu)
            companion = next(player for player in game.players if player.is_cpu)
            self.assertEqual((human.character, human.binding), ("black_dave", {"type": "keyboard"}))
            self.assertEqual(companion.character, "shelly")
            self.assertIsNone(game.ko_companion)
            self.assertEqual(len(game.chiefs), 1)
            self.assertIs(game.chiefs[0].owner, companion)
        finally:
            game.close()
            manager.close()

    def test_controller_can_choose_shelly_with_cpu_dave_and_shared_chief(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        instance_id = 41
        manager.add_synthetic_controller(instance_id)
        game = FadesGame(manager, mute=True)
        try:
            game.state = "title"
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_START)
            self.assertEqual(game.state, "character_select")
            self.assertFalse(game.select_slots[0].confirmed)

            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_DPAD_RIGHT)
            self.assertEqual(game.select_slots[0].character_index, 1)
            self.assertEqual(
                game._selection_footer_lines()[0],
                "YOU CONTROL: SHELLY  •  CPU COMPANION: BLACK DAVE",
            )
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_A)
            self.assertTrue(game.select_slots[0].confirmed)
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_A)

            human = next(player for player in game.players if not player.is_cpu)
            companion = next(player for player in game.players if player.is_cpu)
            self.assertEqual(
                (human.character, human.binding),
                ("shelly", {"type": "controller", "instance_id": instance_id}),
            )
            self.assertEqual(companion.character, "black_dave")
            self.assertIsNone(game.ko_companion)
            self.assertEqual(len(game.chiefs), 1)
            self.assertIs(game.chiefs[0].owner, human)
        finally:
            game.close()
            manager.close()

    def test_controller_can_choose_ko_as_cpu_support_without_creating_player_placeholder(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        instance_id = 43
        manager.add_synthetic_controller(instance_id)
        game = FadesGame(manager, mute=True)
        try:
            game.state = "title"
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_START)
            self.assertEqual(game.state, "character_select")
            self.assertFalse(game.select_slots[0].confirmed)

            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_DPAD_DOWN)
            self.assertEqual(game.select_slots[0].cpu_companion_index, 2)
            self.assertEqual(
                game._selection_footer_lines()[0],
                "YOU CONTROL: BLACK DAVE  •  CPU COMPANION: KO",
            )
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_A)
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_A)

            self.assertEqual(len(game.players), 1)
            self.assertEqual(game.players[0].character, "black_dave")
            self.assertFalse(game.players[0].is_cpu)
            self.assertIsInstance(game.ko_companion, KOCompanion)
            assert game.ko_companion is not None
            self.assertIs(game.ko_companion.owner, game.players[0])
            self.assertFalse(any(player.character == "ko" for player in game.players))
        finally:
            game.close()
            manager.close()

    def test_confirm_entry_keys_can_still_choose_ko_cpu_support(self) -> None:
        keyboard_manager = InputManager(max_players=4, discover_controllers=False)
        keyboard_game = FadesGame(keyboard_manager, mute=True)
        controller_manager = InputManager(max_players=4, discover_controllers=False)
        instance_id = 44
        controller_manager.add_synthetic_controller(instance_id)
        controller_game = FadesGame(controller_manager, mute=True)
        try:
            keyboard_game.state = "title"
            self._tap_key(keyboard_game, keyboard_manager, pygame.K_RETURN)
            self.assertEqual(keyboard_game.state, "character_select")
            self.assertTrue(keyboard_game.select_slots[0].confirmed)
            self._tap_key(keyboard_game, keyboard_manager, pygame.K_DOWN)
            self.assertFalse(keyboard_game.select_slots[0].confirmed)
            self.assertEqual(keyboard_game.select_slots[0].cpu_companion_index, 2)

            controller_game.state = "title"
            self._tap_controller(
                controller_game,
                controller_manager,
                instance_id,
                pygame.CONTROLLER_BUTTON_A,
            )
            self.assertEqual(controller_game.state, "character_select")
            self.assertTrue(controller_game.select_slots[0].confirmed)
            self._tap_controller(
                controller_game,
                controller_manager,
                instance_id,
                pygame.CONTROLLER_BUTTON_DPAD_DOWN,
            )
            self.assertFalse(controller_game.select_slots[0].confirmed)
            self.assertEqual(controller_game.select_slots[0].cpu_companion_index, 2)
        finally:
            keyboard_game.close()
            keyboard_manager.close()
            controller_game.close()
            controller_manager.close()

    def test_controller_can_cycle_past_ko_and_start_with_cpu_white_dave(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        instance_id = 45
        manager.add_synthetic_controller(instance_id)
        game = FadesGame(manager, mute=True)
        try:
            game.state = "title"
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_START)
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_DPAD_DOWN)
            self.assertEqual(game.select_slots[0].cpu_companion_index, 2)
            game.select_slots[0].nav_cooldown = 0.0
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_DPAD_DOWN)
            self.assertEqual(
                game.select_slots[0].cpu_companion_index,
                SOLO_CPU_COMPANIONS.index("white_dave"),
            )
            self.assertIn("CPU COMPANION: WHITE DAVE", game._selection_footer_lines()[0])
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_A)
            self._tap_controller(game, manager, instance_id, pygame.CONTROLLER_BUTTON_A)
            cpu_players = [player for player in game.players if player.is_cpu]
            self.assertEqual([player.character for player in cpu_players], ["white_dave"])
            self.assertIsNone(game.ko_companion)
        finally:
            game.close()
            manager.close()

    def test_two_player_selection_keeps_both_human_owners_and_one_shared_chief(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        instance_id = 42
        manager.add_synthetic_controller(instance_id)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [
                SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True),
                SelectSlot(
                    {"type": "controller", "instance_id": instance_id},
                    character_index=1,
                    confirmed=True,
                ),
            ]
            self.assertIn("EACH PLAYER CONTROLS", game._selection_footer_lines()[0])
            game._start_stage()
            self.assertEqual(
                [(player.character, player.binding, player.is_cpu) for player in game.players],
                [
                    ("black_dave", {"type": "keyboard"}, False),
                    ("shelly", {"type": "controller", "instance_id": instance_id}, False),
                ],
            )
            self.assertEqual(len(game.chiefs), 1)
            self.assertIs(game.chiefs[0].owner, game.players[1])
            self.assertIsNone(game.ko_companion)
        finally:
            game.close()
            manager.close()

    def test_mouse_can_choose_a_character_start_and_use_pause_menu(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.state = "title"
            click = lambda point: game.handle_events([
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": point})
            ])
            click((230, 313))
            self.assertEqual(game.state, "character_select")
            click((244, 120))  # Shelly card
            self.assertEqual(game.select_slots[0].character_index, 1)
            click((400, 120))  # Jermaine is the newly unlocked third hero.
            self.assertEqual(game.select_slots[0].character_index, 2)
            click((556, 120))  # White Dave is the fourth hero.
            self.assertEqual(game.select_slots[0].character_index, 3)
            self.assertNotIn("DEFAULT", " ".join(game._selection_footer_lines()))
            canvas = pygame.Surface((640, 360))
            with mock.patch.object(game, "_text") as draw_text:
                game._draw_character_select(canvas)
            rendered_labels = [call.args[2] for call in draw_text.call_args_list]
            self.assertIn("CHOOSE WHO YOU CONTROL", rendered_labels)
            self.assertIn("SHELLY + CHIEF", rendered_labels)
            self.assertIn("JERMAINE", rendered_labels)
            self.assertIn("WHITE DAVE", rendered_labels)
            self.assertGreaterEqual(rendered_labels.count("WHITE DAVE"), 2)
            self.assertIn("KO", rendered_labels)
            self.assertIn("CPU SUPPORT", rendered_labels)
            self.assertIn("YOU CONTROL: WHITE DAVE  •  CPU COMPANION: SHELLY", rendered_labels)
            self.assertNotIn("LOCKED", rendered_labels)
            click((86, 275))   # ready
            self.assertTrue(game.select_slots[0].confirmed)
            click((86, 275))   # start
            self.assertEqual(game.state, "gameplay")
            human = next(player for player in game.players if not player.is_cpu)
            companion = next(player for player in game.players if player.is_cpu)
            self.assertEqual((human.character, companion.character), ("white_dave", "shelly"))
            self.assertIs(game.chiefs[0].owner, companion)

            game._open_pause_menu(source="test")
            game.handle_events([pygame.event.Event(pygame.MOUSEMOTION, {"pos": (320, 154), "rel": (0, 0), "buttons": (0, 0, 0)})])
            self.assertEqual(game.pause_selection, 1)
            click((320, 154))
            self.assertEqual(game.pause_page, "controls")
            click((320, 170))
            self.assertEqual(game.pause_page, "menu")
            click((320, 106))
            self.assertFalse(game.pause)

            game._go_title()
            self.assertEqual(game.state, "title")
            self.assertEqual((game.select_slots, game.players, game.chiefs), ([], [], []))
            click((230, 313))
            self.assertEqual(game.state, "character_select")
            self.assertEqual(game.select_slots[0].character_index, 0)
        finally:
            game.close()
            manager.close()

    def test_mouse_cpu_cards_choose_ko_and_multiplayer_suppresses_solo_support(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.state = "title"
            game.handle_events([
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (230, 313)})
            ])
            solo_rects = game._character_select_lower_card_rects()
            self.assertEqual(len(solo_rects), 5)
            self.assertTrue(all(pygame.Rect(0, 0, 640, 360).contains(rect) for rect in solo_rects))
            self.assertTrue(all(left.right < right.left for left, right in zip(solo_rects, solo_rects[1:])))
            game.handle_events([
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": solo_rects[3].center})
            ])
            self.assertEqual(game.select_slots[0].cpu_companion_index, 2)
            self.assertIn("CPU COMPANION: KO", game._selection_footer_lines()[0])

            game.handle_events([
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": solo_rects[4].center})
            ])
            self.assertEqual(game.select_slots[0].cpu_companion_index, 3)
            self.assertIn("CPU COMPANION: WHITE DAVE", game._selection_footer_lines()[0])

            extra_rects = game._extra_cpu_companion_card_rects()
            game.handle_events([
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": extra_rects[0].center})
            ])
            game.handle_events([
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": extra_rects[1].center})
            ])
            self.assertIsNotNone(game.select_slots[0].cpu_companion_index_2)
            self.assertIsNotNone(game.select_slots[0].cpu_companion_index_3)
            self.assertEqual(len(game._solo_cpu_companions(game.select_slots[0])), 3)

            game.select_slots.append(
                SelectSlot(
                    {"type": "controller", "instance_id": 99},
                    character_index=1,
                    confirmed=True,
                )
            )
            multiplayer_rects = game._character_select_lower_card_rects()
            self.assertEqual(
                tuple((rect.x, rect.y, rect.w, rect.h) for rect in multiplayer_rects),
                tuple((16 + index * 156, 229, 144, 91) for index in range(4)),
            )
            game.select_slots[0].confirmed = True
            game._start_stage()
            self.assertEqual(len(game.players), 2)
            self.assertTrue(all(not player.is_cpu for player in game.players))
            self.assertIsNone(game.ko_companion)
        finally:
            game.close()
            manager.close()

    def test_jerry_outro_waits_for_click_and_renders_opaque_above_cinematic_tint(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [
                SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
            ]
            game._start_stage()
            game._start_level_outro()
            assert game.level_outro is not None

            # A very large elapsed step only completes Jerry's arrival motion.
            game._update_gameplay(game.level_outro.total_seconds)
            self.assertIsNotNone(game.level_outro)
            assert game.level_outro_frame is not None
            self.assertEqual(game.level_outro_frame.beat, "arrival")
            self.assertTrue(game.level_outro_frame.awaiting_continue)

            # A click is latched through the fixed update and advances exactly
            # one beat. A second update without a click cannot advance again.
            game.handle_events([
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (320, 180)})
            ])
            game._update_gameplay(1.0 / 60.0)
            assert game.level_outro_frame is not None
            self.assertEqual(game.level_outro_frame.beat, "warning")
            game._update_gameplay(10.0)
            assert game.level_outro_frame is not None
            self.assertEqual(game.level_outro_frame.beat, "warning")

            opaque_marker = (251, 97, 42, 255)
            jerry = pygame.Surface((10, 20), pygame.SRCALPHA)
            jerry.fill(opaque_marker)
            canvas = pygame.Surface((640, 360))
            canvas.fill((19, 33, 47))
            with mock.patch("src.game.sprite_atlas.jerry_frame", return_value=jerry), mock.patch.object(
                game, "_text"
            ) as draw_text:
                game._draw_level_outro_overlay(canvas)

            jerry_world = game.projection.project(
                WorldPoint(float(game.meta["stage_width"]) - 118.0, 274.0),
                camera_x=game._render_camera_x,
                camera_depth=game._projection_depth_origin,
                screen_shake=(0.0, game._camera_shake_y),
            )
            # If the tint were composited after Jerry, this exact opaque color
            # would be blended. This sample proves the sprite remains solid.
            self.assertEqual(
                canvas.get_at((int(jerry_world.x), int(jerry_world.y) - 8)),
                opaque_marker,
            )
            rendered_labels = [call.args[2] for call in draw_text.call_args_list]
            self.assertIn("PRESS A BUTTON TO CONTINUE", rendered_labels)
        finally:
            game.close()
            manager.close()

    def test_jerry_outro_accepts_keyboard_and_controller_confirmations(self) -> None:
        cases = (
            ("keyboard", None, pygame.K_SPACE),
            ("controller", 73, pygame.CONTROLLER_BUTTON_A),
        )
        for input_type, instance_id, button in cases:
            with self.subTest(input_type=input_type):
                manager = InputManager(max_players=4, discover_controllers=False)
                if instance_id is not None:
                    manager.add_synthetic_controller(instance_id)
                    binding = {"type": "controller", "instance_id": instance_id}
                else:
                    binding = {"type": "keyboard"}
                game = FadesGame(manager, mute=True)
                try:
                    game.select_slots = [SelectSlot(binding, character_index=0, confirmed=True)]
                    game._start_stage()
                    game._start_level_outro()
                    assert game.level_outro is not None
                    game._update_gameplay(game.level_outro.arrival_seconds)

                    if instance_id is None:
                        self._tap_key(game, manager, int(button))
                    else:
                        self._tap_controller(game, manager, instance_id, int(button))
                    assert game.level_outro_frame is not None
                    self.assertEqual(game.level_outro_frame.beat, "warning")
                finally:
                    game.close()
                    manager.close()

    def test_penultimate_clear_transitions_to_boss_then_results(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [
                SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
            ]
            finale = campaign_levels(game.data)[-1]
            game._select_campaign_level(str(finale["id"]))
            game._start_stage()
            human = next(player for player in game.players if not player.is_cpu)
            game.level_stats.advance(12.5)
            game.record_player_damage(7.5)

            boss_index = len(game.data["encounters"]) - 1
            game.encounter_index = boss_index - 1
            game.encounter_active = True
            game.spawn_queue.clear()
            game.enemies.clear()

            game._update_encounters(0.0)
            transition = game.boss_transition
            self.assertIsNotNone(transition)
            assert transition is not None
            self.assertEqual(game.encounter_index, boss_index)
            self.assertFalse(game.encounter_active)
            self.assertTrue(all(player.state in {"idle", "eliminated", "downed"} for player in game.players))
            self.assertTrue(all(chief.state == "sit" for chief in game.chiefs))

            loading_time_before = game.level_stats.elapsed_seconds
            blank = pygame.Surface((640, 360))
            blank.fill((17, 23, 31))
            unchanged = blank.copy()
            game._draw_boss_loading_overlay(blank)
            self.assertEqual(pygame.image.tobytes(blank, "RGB"), pygame.image.tobytes(unchanged, "RGB"))
            game._update_gameplay(0.05)
            self.assertEqual(game.level_stats.elapsed_seconds, loading_time_before)

            game._update_boss_transition(transition.relocate_seconds)
            self.assertGreater(
                min(player.x for player in game.players),
                float(game.data["transitions"]["boss_loading"]["party_x"]) - 120.0,
            )
            self.assertAlmostEqual(
                game.camera_x,
                float(game.data["encounters"][boss_index]["camera_x"]),
            )
            self.assertGreater(min(player.x for player in game.players) - game.camera_x, 80.0)

            comic = pygame.Surface((640, 360))
            comic.fill((17, 23, 31))
            game._update_boss_transition(0.1)
            with mock.patch("src.game.pixel_art.draw_bmx_bike") as duplicate_bmx:
                game._draw_boss_loading_overlay(comic)
            duplicate_bmx.assert_not_called()
            self.assertNotEqual(pygame.image.tobytes(comic, "RGB"), pygame.image.tobytes(pygame.Surface((640, 360)), "RGB"))

            game._update_boss_transition(
                transition.duration_seconds - transition.relocate_seconds
            )
            self.assertIsNone(game.boss_transition)
            self.assertTrue(game.encounter_active)
            self.assertEqual(game.spawn_queue, ["couch"])

            game._update_encounters(0.0)
            boss = next(enemy for enemy in game.enemies if enemy.kind == "couch")
            boss.update(game, boss.state_duration)
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
            assert game.completion_stats is not None
            self.assertEqual(game.completion_stats.damage_taken, 7.5)
            self.assertEqual(game.completion_stats.completion_seconds, 12.5)
            self.assertEqual(
                game.completion_stats.combined_score,
                sum(player.score for player in game.players),
            )

            for _ in range(50):
                game.update(0.05)
            self.assertTrue(game.victory_frame.show_results)
            self.assertEqual(game.victory_frame.phase, "results")
            game._open_epilogue()
            self.assertEqual(game.state, "epilogue")
            sunset = pygame.Surface((640, 360))
            game.draw(sunset)
            self.assertGreater(pygame.mask.from_surface(sunset).count(), 10_000)
            game.epilogue_selection = 0
            game._activate_epilogue_selection()
            self.assertEqual(game.state, "interlevel")
            self.assertEqual(game.pending_level_id, "chapter_2_level_1")
        finally:
            game.close()
            manager.close()

    def test_chief_bite_animation_starts_at_a_stable_frame(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [
                SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
            ]
            game._start_stage()
            chief = game.chiefs[0]
            frenzy_target = Enemy(9001, "stick", chief.x, chief.y, game.data["enemies"]["stick"])
            frenzy_target.state = "chase"
            frenzy_target.cooldown = 99.0
            game.enemies = [frenzy_target]
            chief.frenzy = 1.0
            chief.attack_cooldown = 0.0
            chief.update(game, 1.0 / 60.0)
            self.assertAlmostEqual(chief.bite_flash, 0.22)
            canvas = pygame.Surface((640, 360))
            with mock.patch("src.game.pixel_art.draw_chief") as draw_chief:
                game.frame = 7
                game._draw_gameplay(canvas)
                first_tick = draw_chief.call_args.kwargs["frame"]
                game.frame = 113
                game._draw_gameplay(canvas)
                second_tick = draw_chief.call_args.kwargs["frame"]
            self.assertEqual((first_tick, second_tick), (0, 0))
        finally:
            game.close()
            manager.close()

    def test_final_clear_wins_over_same_tick_party_elimination(self) -> None:
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
            for player in game.players:
                player.state = "eliminated"

            game._update_gameplay(1.0 / 60.0)

            self.assertEqual(game.state, "gameplay")
            self.assertIsNotNone(game.level_outro)
            game._update_level_outro(0.0, [InputSnapshot(pressed={"dodge"})])
            self.assertEqual(game.state, "complete")
            self.assertIsNotNone(game.completion_stats)
            self.assertTrue(game.level_stats.finished)
        finally:
            game.close()
            manager.close()

    def test_f4_opens_fixed_cross_platform_visual_evidence_scene(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.handle_events([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F4})])

            self.assertEqual(game.state, "gameplay")
            self.assertEqual(game.level_id, "chapter_1_level_1")
            self.assertEqual(game.camera_x, 800.0)
            self.assertEqual(game._render_camera_x, 800.0)
            self.assertEqual(game.encounter_index, len(game.data["encounters"]))
            self.assertFalse(game.encounter_active)
            self.assertFalse(game.debug)
            self.assertEqual([player.character for player in game.players], ["black_dave", "shelly"])
            self.assertFalse(game.enemies)
        finally:
            game.close()
            manager.close()

    def test_treat_release_sound_event_and_art_change_share_one_milestone(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.victory_timeline.reset()
            game.victory_frame = game.victory_timeline.advance(game.victory_timeline.hug_seconds)
            game.victory_frame = game.victory_timeline.advance(
                game.victory_timeline.treat_release_seconds - 0.01
            )
            self.assertEqual(game._victory_art_index(), 11)

            game.victory_frame = game.victory_timeline.advance(0.02)
            self.assertIn("treat_release", game.victory_frame.events)
            self.assertEqual(game._victory_art_index(), 12)
        finally:
            game.close()
            manager.close()


if __name__ == "__main__":
    unittest.main()
