from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.animation_manifest import action_segment_tick, enemy_animation_actor
from src.chapter_content import compile_level_content, load_chapter_content
from src.enemy_variants import apply_enemy_variant_profile
from src.entities import Projectile
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager
from src.pixel_art import draw_projectile
from src import sprite_atlas


HOMELESS_MODELS = (
    "encampment_bottle_scarf",
    "encampment_bottle_puffer",
    "encampment_tire_slinger",
    "underpass_tire_runner",
    "cart_tent_bottle_pitcher",
)
SECURITY_MODELS = (
    "mall_security_watch",
    "event_security_heavy",
    "night_security_patrol",
)
POLICE_MODELS = (
    "city_patrol_nightstick",
    "transit_patrol_nightstick",
    "riot_line_nightstick",
    "bike_patrol_taser",
    "tactical_taser_unit",
)
NEW_MODELS = (*HOMELESS_MODELS, *SECURITY_MODELS, *POLICE_MODELS)


class EnemyRosterExpansionTests(unittest.TestCase):
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
        self.catalog = self.game.enemy_variant_catalog

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def test_catalog_defines_exact_requested_model_and_weapon_counts(self) -> None:
        self.assertTrue(set(NEW_MODELS).issubset(self.catalog))
        self.assertEqual([self.catalog[item]["runtime_kind"] for item in HOMELESS_MODELS], ["homeless"] * 5)
        self.assertEqual([self.catalog[item]["runtime_kind"] for item in SECURITY_MODELS], ["security"] * 3)
        self.assertEqual([self.catalog[item]["runtime_kind"] for item in POLICE_MODELS], ["police"] * 5)
        self.assertEqual(
            [self.catalog[item]["attack_style"] for item in HOMELESS_MODELS],
            ["glass_bottle", "glass_bottle", "bike_tire", "bike_tire", "glass_bottle"],
        )
        self.assertEqual(
            [self.catalog[item]["attack_style"] for item in POLICE_MODELS],
            ["nightstick", "nightstick", "nightstick", "taser", "taser"],
        )

    def test_every_requested_model_round_trips_through_live_enemy_factory(self) -> None:
        for variant_id in NEW_MODELS:
            with self.subTest(variant=variant_id):
                enemy = self.game._spawn_enemy(variant_id)
                expected = self.catalog[variant_id]
                self.assertEqual(enemy.variant_id, variant_id)
                self.assertEqual(enemy.kind, expected["runtime_kind"])
                self.assertEqual(enemy.stats["attack_style"], expected["attack_style"])
                self.assertEqual(enemy.stats["display_name"], expected["display_name"])
                if expected["attack_style"] == "taser":
                    self.assertEqual(enemy.stats["attack_range"], enemy.stats["ranged_attack_range"])
                self.game.enemies.remove(enemy)

    def test_variant_profiles_can_tune_function_and_color_without_new_code_paths(self) -> None:
        synthetic_variant = {
            "runtime_kind": "homeless",
            "display_name": "SYNTHETIC BOTTLE SLINGER",
            "attack_style": "glass_bottle",
            "fictional_role": "synthetic bottle slinger",
            "behavior_note": "uses the generic homeless runtime but reads as a tougher themed variant",
            "stat_multipliers": {"health": 1.35, "damage": 1.10, "speed": 0.92, "cooldown": 0.85},
            "render_tint": [182, 128, 92],
        }
        base_stats = self.game.data["enemies"]["homeless"]
        tuned = apply_enemy_variant_profile(base_stats, synthetic_variant)
        self.assertGreater(tuned["health"], base_stats["health"])
        self.assertLess(tuned["speed"], base_stats["speed"])
        self.assertEqual(tuned["render_tint"], (182, 128, 92))

        self.game.enemy_variant_catalog["synthetic_bottle_slinger"] = synthetic_variant
        enemy = self.game._spawn_enemy("synthetic_bottle_slinger")
        try:
            self.assertEqual(enemy.kind, "homeless")
            self.assertEqual(enemy.stats["attack_style"], "glass_bottle")
            self.assertEqual(enemy.stats["render_tint"], (182, 128, 92))
            self.assertGreater(enemy.stats["health"], base_stats["health"])

            surface = pygame.Surface((640, 360), pygame.SRCALPHA)
            with mock.patch("src.pixel_art.draw_enemy", return_value=pygame.Rect(0, 0, 1, 1)) as draw_enemy:
                self.game.enemies = [enemy]
                self.game._draw_gameplay(surface)

            self.assertEqual(draw_enemy.call_args.kwargs["tint"], (182, 128, 92))
        finally:
            self.game.enemies.remove(enemy)
            self.game.enemy_variant_catalog.pop("synthetic_bottle_slinger", None)

    def test_requested_models_are_reachable_in_authored_waves_and_compact_solo_queues(self) -> None:
        content = load_chapter_content(gameplay=self.game.data)
        authored_ids: set[str] = set()
        compact_ids: set[str] = set()
        for level in content["levels"]:
            compiled = compile_level_content(content, level["runtime_level_id"], 1)
            for encounter in [
                *compiled["major_fights"],
                *compiled["ambush_or_optional"],
                *compiled["environmental_events"],
            ]:
                groups = encounter.get("spawn_groups", ())
                wave = self.game._spawn_identifiers_from_groups(groups)
                authored_ids.update(wave)
                compact_ids.update(
                    self.game._spawn_identifiers_from_groups(groups, focused_limit=4)
                )
        self.assertTrue(set(NEW_MODELS).issubset(authored_ids))
        self.assertTrue(set(NEW_MODELS).issubset(compact_ids))

    def test_weapon_profiles_dispatch_melee_and_projectiles(self) -> None:
        self.human.x = 430.0
        self.human.y = 270.0
        for variant_id in NEW_MODELS:
            with self.subTest(variant=variant_id):
                self.game.projectiles.clear()
                enemy = self.game._spawn_enemy(variant_id)
                enemy.x = 260.0
                enemy.y = self.human.y
                enemy.target_slot = self.human.slot
                enemy._begin_attack(self.game, self.human)
                enemy._execute_attack(self.game)
                attack_style = self.catalog[variant_id]["attack_style"]
                if attack_style in {"glass_bottle", "bike_tire", "taser"}:
                    self.assertEqual([projectile.kind for projectile in self.game.projectiles], [attack_style])
                    self.assertEqual(enemy.state, "attack")
                    self.assertAlmostEqual(enemy.state_duration, float(enemy.stats["active"]))
                    enemy.update(self.game, enemy.state_duration + 0.001)
                    self.assertEqual(enemy.state, "recovery")
                else:
                    self.assertEqual(self.game.projectiles, [])
                    self.assertEqual(enemy.state, "attack")
                self.game.release_attack_token(enemy)
                self.game.enemies.remove(enemy)

    def test_taser_uses_projectile_hitstun_and_throwables_keep_material_landings(self) -> None:
        self.cpu.state = "eliminated"
        self.human.invulnerable = 0.0
        taser = Projectile(
            x=self.human.x - 28.0,
            y=self.human.y,
            z=18.0,
            vx=420.0,
            vy=0.0,
            vz=0.0,
            damage=4.0,
            owner_team="enemy",
            kind="taser",
            ttl=0.5,
            owner_id=900,
            attack_instance_id=3,
            hitstun=0.78,
            knockback=5.0,
        )
        taser.update(self.game, 0.1)
        self.assertTrue(taser.spent)
        self.assertEqual(self.human.state, "hurt")
        self.assertAlmostEqual(self.human.state_duration, 0.78)
        self.assertIn("STUNNED!", {effect.text for effect in self.game.effects if effect.kind == "text"})

        self.game.effects.clear()
        bottle = Projectile(1000.0, 20.0, 1.0, 0.0, 0.0, -80.0, 5.0, "enemy", kind="glass_bottle")
        bottle.update(self.game, 0.02)
        self.assertTrue(bottle.spent)
        self.assertTrue({"spark", "impact"}.issubset({effect.kind for effect in self.game.effects}))

        tire = Projectile(1000.0, 20.0, 1.0, 0.0, 0.0, -120.0, 5.0, "enemy", kind="bike_tire")
        tire.update(self.game, 0.02)
        self.assertFalse(tire.spent)
        self.assertGreater(tire.vz, 28.0)

    def test_runtime_attack_timing_and_game_draw_support_all_new_roles(self) -> None:
        for variant_id in NEW_MODELS:
            runtime_kind = self.catalog[variant_id]["runtime_kind"]
            with self.subTest(variant=variant_id):
                actor = enemy_animation_actor(runtime_kind, variant_id)
                self.assertGreaterEqual(action_segment_tick(actor, "attack", "active", 0.05, 0.16), 0)
                enemy = self.game._spawn_enemy(variant_id)
                enemy.x, enemy.y = 250.0, 270.0
                enemy._set_state("windup", 0.42)
                enemy.state_clock = 0.20
                self.game.enemies = [enemy]
                surface = pygame.Surface((640, 360), pygame.SRCALPHA)
                self.game._draw_gameplay(surface)
                self.assertGreater(pygame.mask.from_surface(surface).count(), 1000)

                self.assertIsNotNone(
                    sprite_atlas.enemy_frame(runtime_kind, "attack", 4, variant_id=variant_id)
                )
        with self.assertRaisesRegex(ValueError, "unknown enemy kind"):
            sprite_atlas.enemy_frame("prototype_enemy", "idle", 0)

    def test_throwable_and_taser_projectile_art_is_distinct_and_crisp(self) -> None:
        signatures: set[bytes] = set()
        for kind in ("glass_bottle", "bike_tire", "taser"):
            surface = pygame.Surface((100, 80), pygame.SRCALPHA)
            rect = draw_projectile(surface, 50, 42, 8, 1, kind, 2)
            self.assertGreater(pygame.mask.from_surface(surface).count(), 12)
            self.assertGreater(rect.w, 8)
            signatures.add(pygame.image.tobytes(surface, "RGBA"))
        self.assertEqual(len(signatures), 3)

        # A thrown tire needs a readable hollow rubber center. Filling that
        # center with four cardinal spokes makes the gameplay sprite look like
        # a target/debug reticle at native resolution.
        for frame in range(4):
            tire_surface = pygame.Surface((100, 80), pygame.SRCALPHA)
            draw_projectile(tire_surface, 50, 42, 8, 1, "bike_tire", frame)
            self.assertEqual(tire_surface.get_at((50, 34)).a, 0)


if __name__ == "__main__":
    unittest.main()
