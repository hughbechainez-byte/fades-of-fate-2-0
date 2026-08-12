"""Focused contracts for Dave's pose-bound flame presentation."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src import pixel_art, sprite_atlas
from src.animation_manifest import ANIMATION_CLIPS
from src.config import LOGICAL_SIZE
from src.entities import Enemy
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DaveFlameVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode(LOGICAL_SIZE)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_flames_follow_authored_hands_for_poses_facing_and_jump_height(self) -> None:
        world_x, world_y = 260, 248
        for clip in (candidate for candidate in ANIMATION_CLIPS if candidate.actor == "black_dave"):
            state = clip.state
            for phase in range(clip.frame_count):
                tick = phase * clip.hold
                authored = sprite_atlas.player_frame("black_dave", state, tick)
                anchors = sprite_atlas.player_fist_anchors("black_dave", state, tick)
                self.assertIsNotNone(authored)
                self.assertEqual(len(anchors), 2)
                assert authored is not None
                left = world_x - authored.get_width() // 2
                top = world_y - (authored.get_height() - 4)

                for facing in (1, -1):
                    with self.subTest(state=state, phase=phase, facing=facing):
                        canvas = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
                        flame_rect = pixel_art.draw_fist_flames(
                            canvas,
                            world_x,
                            world_y,
                            facing=facing,
                            frame=19,
                            state=state,
                            sprite_tick=tick,
                        )
                        for anchor_x, anchor_y in anchors:
                            screen_x = left + (anchor_x if facing > 0 else authored.get_width() - 1 - anchor_x)
                            screen_y = top + anchor_y
                            self.assertTrue(flame_rect.collidepoint(screen_x, screen_y))
                            self.assertGreater(canvas.get_at((screen_x, screen_y)).a, 0)

                if phase == 0:
                    grounded = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
                    airborne = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
                    ground_rect = pixel_art.draw_fist_flames(
                        grounded,
                        world_x,
                        world_y,
                        frame=19,
                        state=state,
                        sprite_tick=tick,
                    )
                    air_rect = pixel_art.draw_fist_flames(
                        airborne,
                        world_x,
                        world_y,
                        frame=19,
                        z=31.0,
                        state=state,
                        sprite_tick=tick,
                    )
                    self.assertEqual((air_rect.x, air_rect.y), (ground_rect.x, ground_rect.y - 31))

    def test_strike_overlay_and_contact_effects_are_visually_distinct(self) -> None:
        idle = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        strike = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        pixel_art.draw_fist_flames(idle, 250, 245, state="idle", sprite_tick=0, frame=7)
        pixel_art.draw_fist_flames(strike, 250, 245, state="attack_1", sprite_tick=0, frame=7)
        idle_pixels = pygame.mask.from_surface(idle).count()
        strike_pixels = pygame.mask.from_surface(strike).count()
        self.assertGreater(strike_pixels, idle_pixels)

        signatures: set[tuple[tuple[int, int], bytes]] = set()
        for kind, y in (("flame_trail_right", 180), ("flame_burst", 220), ("scorch", 260), ("enemy_fire", 300)):
            canvas = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
            rect = pixel_art.draw_effect(canvas, 300, y, kind=kind, frame=2, radius=30)
            self.assertGreater(rect.w * rect.h, 0)
            crop = canvas.subsurface(rect.clip(canvas.get_rect())).copy()
            signatures.add((crop.get_size(), pygame.image.tobytes(crop, "RGBA")))
        self.assertEqual(len(signatures), 4)

    def test_rgb_gameplay_canvas_keeps_flame_overlay_compact_and_transparent(self) -> None:
        canvas = pygame.Surface(LOGICAL_SIZE)
        canvas.fill((7, 11, 19))
        rect = pixel_art.draw_fist_flames(
            canvas,
            320,
            240,
            facing=1,
            state="attack_1",
            sprite_tick=0,
            frame=0,
        )
        self.assertLess(rect.w, 90)
        self.assertLess(rect.h, 70)
        for point in ((0, 0), (639, 359), (320, 0), (0, 240)):
            self.assertEqual(canvas.get_at(point)[:3], (7, 11, 19))

    def test_flames_have_layered_palette_animation_sparks_and_heat_contours(self) -> None:
        signatures: set[bytes] = set()
        for phase in range(4):
            canvas = pygame.Surface((420, 260), pygame.SRCALPHA)
            rect = pixel_art.draw_fist_flames(
                canvas,
                210,
                220,
                facing=1,
                frame=phase,
                state="attack_2",
                sprite_tick=phase * 2,
            )
            colors = [
                canvas.get_at((x, y))
                for y in range(max(0, rect.top), min(canvas.get_height(), rect.bottom))
                for x in range(max(0, rect.left), min(canvas.get_width(), rect.right))
                if canvas.get_at((x, y)).a
            ]
            dark_outer = sum(color.r < 110 and color.g < 65 for color in colors)
            red_body = sum(color.r >= 165 and color.g < 115 and color.b < 75 for color in colors)
            orange_mid = sum(color.r >= 235 and 110 <= color.g < 220 and color.b < 110 for color in colors)
            hot_core = sum(color.r >= 245 and color.g >= 220 and color.b >= 120 for color in colors)
            with self.subTest(phase=phase):
                self.assertGreater(dark_outer, 45)
                self.assertGreater(red_body, 70)
                self.assertGreater(orange_mid, 35)
                self.assertGreater(hot_core, 20)
                self.assertGreater(pygame.mask.from_surface(canvas).count(), 500)
            signatures.add(pygame.image.tobytes(canvas, "RGBA"))
        self.assertEqual(len(signatures), 4, "flicker, heat contours and embers must animate")

    def test_flame_detail_qa_sheet_covers_pose_trails_burst_and_enemy_fire(self) -> None:
        output = PROJECT_ROOT / "build" / "flame_detail_qa.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        sheet = pygame.Surface((1120, 620))
        sheet.fill((19, 23, 33))
        font = pygame.font.Font(None, 24)
        sheet.blit(font.render("POSE-BOUND LAYERED FIST FIRE", False, (255, 223, 137)), (22, 14))
        pose_specs = (
            ("idle", 0),
            ("walk", 6),
            ("attack_1", 4),
            ("attack_2", 6),
            ("attack_3", 4),
            ("heavy", 4),
            ("super", 5),
        )
        for index, (state, phase) in enumerate(pose_specs):
            clip = next(clip for clip in ANIMATION_CLIPS if clip.actor == "black_dave" and clip.state == state)
            tick = min(clip.frame_count - 1, phase) * clip.hold
            actor_x = 80 + index * 155
            facing = -1 if index % 2 else 1
            pixel_art.draw_player(sheet, actor_x, 290, 0, facing, state, "black_dave", tick, "#ef5547")
            pixel_art.draw_fist_flames(sheet, actor_x, 290, facing=facing, frame=9 + index, state=state, sprite_tick=tick)
            sheet.blit(font.render(state.upper(), False, (214, 222, 235)), (actor_x - 45, 305))

        sheet.blit(font.render("WHIFF TRAIL / CONTACT BURST / SCORCH / ON-FIRE FEEDBACK", False, (255, 223, 137)), (22, 354))
        effect_specs = (
            ("flame_trail_right", 145, 455, 38),
            ("flame_burst", 415, 455, 38),
            ("scorch", 650, 495, 34),
            ("enemy_fire", 875, 500, 34),
        )
        for kind, effect_x, effect_y, radius in effect_specs:
            pixel_art.draw_effect(sheet, effect_x, effect_y, kind=kind, frame=3, radius=radius)
            sheet.blit(font.render(kind.upper(), False, (214, 222, 235)), (effect_x - 75, 565))

        pygame.image.save(sheet, output)
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 22_000)

    def test_flaming_contact_adds_feedback_without_a_hidden_burn_damage_change(self) -> None:
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        try:
            game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
            game._start_stage()
            dave, shelly = game.players
            shelly.state = "eliminated"
            dave.flaming_fists_timer = 1.0
            target = Enemy(711, "stick", dave.x + 24.0, dave.y, game.data["enemies"]["stick"])
            target.state = "chase"
            game.enemies = [target]
            move = game.data["moves"]["light_combo"][0]
            before = target.health

            self.assertEqual(game.player_attack(dave, move, "light"), 1)

            self.assertAlmostEqual(target.health, before - float(move["damage"]) * 1.20)
            self.assertEqual(target.burn_time, 0.0)
            kinds = {effect.kind for effect in game.effects}
            self.assertTrue({"flame_trail_right", "flame_burst", "scorch", "ember"}.issubset(kinds))
            self.assertGreater(game._dave_flame_visuals[target.enemy_id], 0.0)
            game._update_dave_flame_visuals(0.79)
            self.assertNotIn(target.enemy_id, game._dave_flame_visuals)
            self.assertEqual(target.burn_time, 0.0)
        finally:
            game.close()
            manager.close()


if __name__ == "__main__":
    unittest.main()
