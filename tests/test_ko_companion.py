"""Focused behavioral contracts for KO's autonomous cameo."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src import sprite_atlas
from src.animation_manifest import clip_for
from src.entities import Enemy, KOCompanion, KO_LIGHTNING_STYLES
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


class KOCompanionTests(unittest.TestCase):
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
            SelectSlot(
                {"type": "keyboard"},
                character_index=0,
                confirmed=True,
                cpu_companion_index=2,
            )
        ]
        self.game._start_stage()
        self.ko = self.game.ko_companion
        assert self.ko is not None

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def enemy(
        self,
        enemy_id: int,
        *,
        kind: str = "stick",
        x_offset: float = 80.0,
        y_offset: float = 0.0,
    ) -> Enemy:
        result = Enemy(
            enemy_id,
            kind,
            self.ko.x + x_offset,
            self.ko.y + y_offset,
            self.game.data["enemies"][kind],
        )
        result.state = "chase"
        result.cooldown = 99.0
        return result

    def begin_regular_action(self, target: Enemy) -> str:
        target.x = self.ko.x + 10.0
        target.y = self.ko.y
        self.game.enemies = [target]
        self.ko.attack_cooldown = 0.0
        self.ko.update(self.game, 0.0)
        action = self.ko.pending_action
        self.assertEqual(self.ko.state, "prepare")
        self.ko.update(self.game, float(self.ko.config["warmup_seconds"]))
        self.assertEqual(self.ko.state, "idle")
        self.ko.update(self.game, 0.0)
        self.assertEqual(self.ko.state, action)
        return action

    def test_stage_owns_one_non_player_ko_companion(self) -> None:
        self.assertIsInstance(self.ko, KOCompanion)
        self.assertNotIn(self.ko, self.game.players)
        self.assertEqual(len(self.game.players), 1)
        self.assertTrue(all(player.character != "ko" for player in self.game.players))
        self.assertEqual(sum(isinstance(actor, KOCompanion) for actor in [self.ko]), 1)
        human = next(player for player in self.game.players if not player.is_cpu)
        self.assertIs(self.ko.owner, human)
        self.assertEqual(self.ko.attack_cooldown, 20.0)

    def test_ko_model_height_sits_between_shelly_and_dave(self) -> None:
        def mean_idle_height(actor: str) -> float:
            clip = clip_for(actor, "idle")
            heights: list[int] = []
            for pose in range(clip.frame_count):
                frame = (
                    sprite_atlas.ko_frame("idle", pose * clip.hold)
                    if actor == "ko"
                    else sprite_atlas.player_frame(actor, "idle", pose * clip.hold)
                )
                self.assertIsInstance(frame, pygame.Surface)
                assert frame is not None
                heights.append(frame.get_bounding_rect(min_alpha=1).height)
            return sum(heights) / len(heights)

        shelly_height = mean_idle_height("shelly")
        ko_height = mean_idle_height("ko")
        dave_height = mean_idle_height("black_dave")
        self.assertLess(shelly_height, ko_height)
        self.assertLess(ko_height, dave_height)

    def test_attack_clock_freezes_without_opponents_and_uses_20_to_30_seconds(self) -> None:
        self.ko.update(self.game, 7.0)
        self.assertEqual(self.ko.attack_cooldown, 20.0)

        self.game.enemies = [self.enemy(1)]
        self.ko.update(self.game, 5.0)
        self.assertEqual(self.ko.attack_cooldown, 15.0)
        self.assertEqual(tuple(self.ko.config["attack_intervals"]), (20, 25, 30))

    def test_target_selection_prefers_an_enemy_teammates_are_not_damaging(self) -> None:
        contested = self.enemy(10, x_offset=22.0)
        quiet = self.enemy(11, x_offset=130.0)
        contested.recent_damage_timer = 0.8
        self.game.enemies = [contested, quiet]

        selected = self.game.select_ko_target(self.ko)

        self.assertIs(selected, quiet)
        self.ko.attack_cooldown = 0.0
        self.ko.update(self.game, 0.0)
        self.assertIs(self.ko.target, quiet)
        self.assertTrue(quiet.ko_claimed)
        self.assertFalse(
            quiet.take_damage(10.0, self.game, self.ko.owner),
            "teammates damaged KO's selected opponent during the warm-up",
        )

    def test_target_selection_has_a_bounded_fallback_when_everyone_is_contested(self) -> None:
        contested = self.enemy(12)
        contested.recent_damage_timer = 99.0
        self.game.enemies = [contested]
        self.ko.attack_cooldown = 0.0

        self.ko.update(self.game, 1.19)
        self.assertIsNone(self.ko.target)
        self.ko.update(self.game, 0.02)

        self.assertIs(self.ko.target, contested)
        self.assertEqual(self.ko.state, "prepare")

    def test_claim_tracks_exact_object_not_a_reused_enemy_id(self) -> None:
        original = self.enemy(20)
        replacement = self.enemy(20, x_offset=120.0)
        self.game.enemies = [original]
        self.ko.attack_cooldown = 0.0
        self.ko.update(self.game, 0.0)
        self.assertIs(self.ko.target, original)

        self.game.enemies = [replacement]
        self.ko.update(self.game, 0.1)

        self.assertIsNone(self.ko.target)
        self.assertFalse(original.ko_claimed)
        self.assertFalse(replacement.ko_claimed)
        self.assertEqual(replacement.health, replacement.max_health)

    def test_skateboard_state_requires_applied_motion_and_mirrors_facing(self) -> None:
        target = self.enemy(30, x_offset=180.0)
        target.ko_claimed = True
        self.ko.target = target
        self.ko.pending_action = "punch_1"
        self.game.enemies = [target]

        with mock.patch.object(self.game, "move_actor", return_value=(3.0, 0.0)):
            self.ko.update(self.game, 1.0 / 60.0)
        self.assertEqual(self.ko.state, "skate")
        self.assertEqual(self.ko.facing, 1)

        with mock.patch.object(self.game, "move_actor", return_value=(0.0, 0.0)):
            self.ko.update(self.game, 1.0 / 60.0)
        self.assertEqual(self.ko.state, "idle")

        target.x = self.ko.x - 180.0
        with mock.patch.object(self.game, "move_actor", return_value=(-3.0, 0.0)):
            self.ko.update(self.game, 1.0 / 60.0)
        self.assertEqual(self.ko.state, "skate")
        self.assertEqual(self.ko.facing, -1)

    def test_regular_attacks_rotate_punch_punch_kick(self) -> None:
        observed: list[str] = []
        cooldowns: list[float] = []
        lightning: list[tuple[str, tuple[int, int, int]]] = []
        for index in range(3):
            target = self.enemy(40 + index)
            observed.append(self.begin_regular_action(target))
            effect_start = len(self.game.effects)
            self.ko.update(self.game, float(self.ko.config["attack_seconds"]))
            self.assertEqual(target.state, "ko_dazed")
            self.assertEqual(self.ko.state, "idle")
            cooldowns.append(self.ko.attack_cooldown)
            new_lightning = [
                effect
                for effect in self.game.effects[effect_start:]
                if effect.kind.startswith("ko_lightning_")
            ]
            self.assertEqual(len(new_lightning), 1)
            lightning.append((new_lightning[0].kind, new_lightning[0].color))
        self.assertEqual(observed, ["punch_1", "punch_2", "kick"])
        self.assertEqual(cooldowns, [25.0, 30.0, 20.0])
        self.assertEqual(
            lightning,
            [
                (KO_LIGHTNING_STYLES[action][0], KO_LIGHTNING_STYLES[action][1])
                for action in observed
            ],
        )
        self.assertEqual(len({color for _, color in lightning}), 3)
        self.assertEqual(self.ko.completed_actions, 3)
        self.assertEqual(self.ko.attack_cooldown, 20.0)

    def test_one_hit_dazes_wobbles_falls_and_awards_one_knockout(self) -> None:
        target = self.enemy(50, kind="couch")
        action = self.begin_regular_action(target)
        self.assertEqual(action, "punch_1")
        before_hits = self.ko.owner.hit_count
        before_kos = self.ko.owner.ko_count

        self.ko.update(self.game, float(self.ko.config["attack_impact_seconds"]))

        self.assertEqual(target.health, 0.0)
        self.assertEqual(target.state, "ko_dazed")
        self.assertEqual(self.ko.owner.hit_count, before_hits + 1)
        self.assertEqual(self.ko.owner.ko_count, before_kos)
        self.assertIsNone(self.game.couch_retreat)
        self.assertFalse(
            target.begin_ko_sequence(
                self.game,
                self.ko.owner,
                daze_seconds=2.4,
                fall_seconds=0.62,
            )
        )

        target.update(self.game, float(self.ko.config["daze_seconds"]) + 0.01)
        self.assertEqual(target.state, "ko_fall")
        target.update(self.game, float(self.ko.config["fall_seconds"]) + 0.01)
        self.assertEqual(target.state, "dead")
        self.assertEqual(
            target.state_duration,
            float(self.ko.config["disappear_seconds"]),
        )
        self.assertEqual(self.ko.owner.ko_count, before_kos + 1)
        self.game._update_gameplay(float(self.ko.config["disappear_seconds"]) + 0.01)
        self.assertNotIn(target, self.game.enemies)

    def test_fourth_action_supers_every_current_opponent_without_eating_spawns(self) -> None:
        enemies = [self.enemy(60 + index, x_offset=45.0 + index * 55.0) for index in range(4)]
        self.game.enemies = enemies
        marker = (999, "future_wave")
        self.game.spawn_queue.append(marker)
        before_queue = list(self.game.spawn_queue)
        self.ko.completed_actions = 3
        self.ko.attack_cooldown = 0.0

        self.ko.update(self.game, 0.0)
        self.assertEqual(self.ko.pending_action, "super")
        self.ko.update(self.game, float(self.ko.config["warmup_seconds"]))
        self.assertEqual(self.ko.state, "super")
        self.assertEqual(
            {id(enemy) for enemy in self.ko.super_targets},
            {id(enemy) for enemy in enemies},
        )
        self.ko.update(self.game, float(self.ko.config["super_duration"]))

        self.assertTrue(all(enemy.state == "ko_dazed" for enemy in enemies))
        self.assertTrue(all(enemy.health == 0.0 for enemy in enemies))
        self.assertEqual(self.ko.super_hits, len(enemies))
        self.assertEqual(self.ko.last_action, "super")
        self.assertEqual(self.ko.completed_actions, 4)
        self.assertEqual(self.game.spawn_queue, before_queue)
        super_lightning = [
            effect
            for effect in self.game.effects
            if effect.kind == KO_LIGHTNING_STYLES["super"][0]
        ]
        self.assertEqual(len(super_lightning), len(enemies))
        self.assertTrue(
            all(effect.color == KO_LIGHTNING_STYLES["super"][1] for effect in super_lightning)
        )
        self.assertTrue(all(effect.radius >= KO_LIGHTNING_STYLES["super"][2] for effect in super_lightning))

    def test_super_lightning_faces_a_close_left_target_after_contact_teleport(self) -> None:
        target = self.enemy(64, x_offset=-5.0)
        self.game.enemies = [target]
        self.ko.completed_actions = 3
        self.ko.attack_cooldown = 0.0

        self.ko.update(self.game, 0.0)
        self.ko.update(self.game, float(self.ko.config["warmup_seconds"]))
        self.ko.update(self.game, float(self.ko.config["super_duration"]))

        lightning = [
            effect
            for effect in self.game.effects
            if effect.kind == KO_LIGHTNING_STYLES["super"][0]
        ]
        self.assertEqual(len(lightning), 1)
        self.assertEqual(lightning[0].direction, -1.0)

    def test_render_uses_strict_state_facing_and_moving_daze_stars(self) -> None:
        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        self.ko.state = "prepare"
        self.ko.facing = -1
        self.ko.state_clock = 0.2
        with mock.patch("src.game.pixel_art.draw_ko", create=True) as draw_ko:
            self.game._draw_gameplay(canvas)
        draw_ko.assert_called_once()
        self.assertEqual(draw_ko.call_args.kwargs["state"], "prepare")
        self.assertEqual(draw_ko.call_args.kwargs["facing"], -1)

        first = pygame.Surface((80, 80), pygame.SRCALPHA)
        second = pygame.Surface((80, 80), pygame.SRCALPHA)
        self.game._draw_ko_daze_stars(first, 40.0, 70.0, 0.0, 7)
        self.game._draw_ko_daze_stars(second, 40.0, 70.0, 0.18, 7)
        self.assertNotEqual(
            pygame.image.tobytes(first, "RGBA"),
            pygame.image.tobytes(second, "RGBA"),
        )


if __name__ == "__main__":
    unittest.main()
