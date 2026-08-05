from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src import sprite_atlas
from src.animation_manifest import action_segment_tick, enemy_animation_actor
from src.entities import Projectile
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


WEAPON_VARIANTS = (
    ("encampment_bottle_scarf", "glass_bottle"),
    ("encampment_bottle_puffer", "glass_bottle"),
    ("encampment_tire_slinger", "bike_tire"),
    ("underpass_tire_runner", "bike_tire"),
    ("cart_tent_bottle_pitcher", "glass_bottle"),
    ("mall_security_watch", "security_flashlight"),
    ("event_security_heavy", "security_flashlight"),
    ("night_security_patrol", "security_flashlight"),
    ("city_patrol_nightstick", "nightstick"),
    ("transit_patrol_nightstick", "nightstick"),
    ("riot_line_nightstick", "nightstick"),
    ("bike_patrol_taser", "taser"),
    ("tactical_taser_unit", "taser"),
)
PROJECTILE_STYLES = frozenset({"glass_bottle", "bike_tire", "taser"})


class EnemyWeaponRuntimeTests(unittest.TestCase):
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
        self.game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
        self.game._start_stage()
        self.human = next(player for player in self.game.players if not player.is_cpu)
        self.cpu = next(player for player in self.game.players if player.is_cpu)
        self.cpu.state = "eliminated"
        self.human.x = 400.0
        self.human.y = 270.0

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def _reset_human(self) -> None:
        self.human.health = self.human.max_health
        self.human.invulnerable = 0.0
        self.human.z = 0.0
        self.human.vz = 0.0
        self.human.hitbox_sweep_x = self.human.x
        self.human.hitbox_sweep_y = self.human.y
        self.human.set_state("idle")

    def test_every_requested_weapon_variant_completes_a_live_solo_attack(self) -> None:
        token_limits = [int(limit) for limit in self.game.data["scaling"]["attack_tokens"][:2]]
        self.assertEqual(token_limits, [1, 1])
        self.assertEqual(self.game._scaling_index(), 0)
        self.cpu.is_cpu = False
        self.assertEqual(self.game._scaling_index(), 1)
        self.cpu.is_cpu = True

        for variant_id, expected_style in WEAPON_VARIANTS:
            with self.subTest(variant=variant_id):
                self._reset_human()
                self.game.attack_tokens_used = 0
                self.game.projectiles.clear()
                enemy = self.game._spawn_enemy(variant_id)
                self.game.enemies = [enemy]
                self.assertEqual(enemy.stats["attack_style"], expected_style)
                self.assertEqual(int(enemy.stats["token_cost"]), 1)
                enemy.x = self.human.x - float(enemy.stats["attack_range"]) * 0.75
                enemy.y = self.human.y
                enemy.cooldown = 0.0
                enemy._set_state("chase")
                before = self.human.health
                emitted: set[str] = set()
                observed_states: set[str] = set()

                for _ in range(240):
                    enemy.update(self.game, 1.0 / 60.0)
                    observed_states.add(enemy.state)
                    for projectile in list(self.game.projectiles):
                        emitted.add(projectile.kind)
                        projectile.update(self.game, 1.0 / 60.0)
                    self.game.projectiles = [
                        projectile for projectile in self.game.projectiles if not projectile.spent
                    ]
                    if self.human.health < before and (
                        expected_style not in PROJECTILE_STYLES or expected_style in emitted
                    ):
                        break

                self.assertIn("windup", observed_states)
                self.assertLess(self.human.health, before)
                if expected_style in PROJECTILE_STYLES:
                    self.assertIn(expected_style, emitted)
                else:
                    self.assertEqual(emitted, set())
                self.game.release_attack_token(enemy)

    def test_glass_bottle_resolves_its_final_sweep_before_ground_shatter(self) -> None:
        self._reset_human()
        self.game.effects.clear()
        bottle = Projectile(
            x=self.human.x - 21.0,
            y=self.human.y,
            z=0.1,
            vx=120.0,
            vy=0.0,
            vz=0.0,
            damage=9.0,
            owner_team="enemy",
            kind="glass_bottle",
            ttl=1.0,
            owner_id=901,
            attack_instance_id=7,
        )
        before = self.human.health

        bottle.update(self.game, 1.0 / 60.0)

        self.assertTrue(bottle.spent)
        self.assertEqual(self.human.health, before - 9.0)
        effect_kinds = {effect.kind for effect in self.game.effects}
        self.assertTrue({"hit", "spark", "impact"}.issubset(effect_kinds))

    def test_projectiles_begin_at_the_authored_release_anchor_for_both_facings(self) -> None:
        for variant_id, style in WEAPON_VARIANTS:
            if style not in PROJECTILE_STYLES:
                continue
            enemy = self.game._spawn_enemy(variant_id)
            enemy.x = 260.0
            enemy.y = 270.0
            actor = enemy_animation_actor(enemy.kind, variant_id)
            release_tick = action_segment_tick(
                actor,
                "attack",
                "active",
                0.0,
                float(enemy.stats["active"]),
            )
            frame = sprite_atlas.enemy_frame(
                enemy.kind,
                "attack",
                release_tick,
                variant_id=variant_id,
            )
            root = sprite_atlas.enemy_root_anchor(
                enemy.kind,
                "attack",
                release_tick,
                variant_id=variant_id,
            )
            release = sprite_atlas.enemy_release_anchor(
                enemy.kind,
                "attack",
                release_tick,
                variant_id=variant_id,
            )
            self.assertIsNotNone(frame)
            self.assertIsNotNone(root)
            self.assertIsNotNone(release)
            assert frame is not None and root is not None and release is not None

            for facing in (-1, 1):
                with self.subTest(variant=variant_id, facing=facing):
                    self.game.projectiles.clear()
                    enemy.facing = facing
                    release_x = release[0] if facing > 0 else frame.get_width() - 1 - release[0]
                    root_x = root[0] if facing > 0 else frame.get_width() - 1 - root[0]
                    expected_x = enemy.x + release_x - root_x
                    expected_z = max(0.0, float(root[1] - release[1]))

                    self.game.spawn_enemy_projectile(enemy, self.human, style)

                    self.assertEqual(len(self.game.projectiles), 1)
                    projectile = self.game.projectiles[0]
                    self.assertEqual(projectile.kind, style)
                    self.assertAlmostEqual(projectile.x, expected_x)
                    self.assertAlmostEqual(projectile.y, enemy.y)
                    self.assertAlmostEqual(projectile.z, expected_z)
            self.game.enemies.remove(enemy)

    def test_ballistic_gravity_stops_at_remaining_projectile_lifetime(self) -> None:
        for kind in ("glass_bottle", "bike_tire"):
            with self.subTest(kind=kind):
                self.game.effects.clear()
                projectile = Projectile(
                    x=1000.0,
                    y=20.0,
                    z=30.0,
                    vx=100.0,
                    vy=0.0,
                    vz=50.0,
                    damage=1.0,
                    owner_team="enemy",
                    kind=kind,
                    ttl=0.01,
                )

                projectile.update(self.game, 0.5)

                self.assertTrue(projectile.spent)
                self.assertAlmostEqual(projectile.x, 1001.0)
                self.assertAlmostEqual(projectile.vz, 45.8)
                self.assertAlmostEqual(projectile.z, 30.458)
                self.assertEqual(self.game.effects, [])


if __name__ == "__main__":
    unittest.main()
