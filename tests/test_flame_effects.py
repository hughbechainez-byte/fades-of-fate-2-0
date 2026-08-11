from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from src.character_animation import AnimationEvent, AnimationSample, VfxPlacement, VfxSocket
from src.flame_effects import FlameAtlasCache, FlameAtlasDefinition, FlameCompositor, FlameFrame, FlameLayer, animation_phase


class FlameEffectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((32, 32))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def _definition(self, path: Path) -> FlameAtlasDefinition:
        frames = {name: (FlameFrame(name, (0, 0, 4, 4), (2, 2)), FlameFrame(name, (4, 0, 4, 4), (2, 2))) for name in ("rear_shell", "front_shell", "flame_trail", "flame_burst", "ember", "scorch", "enemy_fire")}
        return FlameAtlasDefinition(path, frames, 10)

    def _sample(self, events: tuple[AnimationEvent, ...] = ()) -> AnimationSample:
        socket = VfxSocket("lead_hand", (14, 8), (1, 0), 4, 1, "front")
        return AnimationSample("black_dave", "attack_z", 2, object(), (10, 20), (0, 0, 20, 30), (), events, (VfxPlacement("rear_shell", socket, "rear"),), (VfxPlacement("front_shell", socket, "front"),))

    def test_atlas_loads_once_and_caches_native_and_mirrored_cels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flames.png"
            image = pygame.Surface((8, 4), pygame.SRCALPHA)
            image.fill((255, 0, 0), (0, 0, 4, 4)); image.fill((0, 255, 0), (4, 0, 4, 4)); pygame.image.save(image, path)
            cache = FlameAtlasCache(); definition = self._definition(path)
            right = cache.frame(definition, "rear_shell", 0.0, 1, strict=True)
            again = cache.frame(definition, "rear_shell", 0.0, 1, strict=True)
            left = cache.frame(definition, "rear_shell", 0.0, -1, strict=True)
            self.assertEqual(cache.load_count, 1); self.assertIs(right[0], again[0]); self.assertEqual(left[0].get_at((3, 0)).r, 255)

    def test_absent_atlas_is_safe_until_v2_is_active_then_fails_closed(self) -> None:
        definition = self._definition(Path("does-not-exist-v2-flames.png"))
        self.assertIsNone(FlameAtlasCache().frame(definition, "rear_shell", 0.0, 1, strict=False))
        with self.assertRaises(FileNotFoundError): FlameAtlasCache().frame(definition, "rear_shell", 0.0, 1, strict=True)

    def test_phase_uses_only_local_execution_time(self) -> None:
        self.assertEqual((animation_phase(0.0, 4, 10), animation_phase(0.19, 4, 10), animation_phase(0.41, 4, 10)), (0, 1, 0))
        self.assertEqual(animation_phase(0.19, 4, 10), animation_phase(10.19, 4, 10))

    def test_socket_mirrors_about_sample_root(self) -> None:
        sample = self._sample(); socket = sample.rear_vfx[0].socket
        self.assertEqual(FlameCompositor.socket_position(sample, socket, (100, 200), 1), (104, 188))
        self.assertEqual(FlameCompositor.socket_position(sample, socket, (100, 200), -1), (96, 188))

    def test_plan_keeps_rear_body_front_contact_order_and_partitions_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flames.png"; pygame.image.save(pygame.Surface((8, 4), pygame.SRCALPHA), path)
            sample = self._sample((AnimationEvent("flame_whiff", 2), AnimationEvent("flame_contact", 2), AnimationEvent("enemy_fire", 2)))
            plan = FlameCompositor(self._definition(path), v2_active=True).plan(sample, (100, 200), 1, 0.1)
            self.assertEqual(tuple(command.layer for command in plan), tuple(sorted(command.layer for command in plan)))
            self.assertEqual(next(command for command in plan if command.asset_id == "body").layer, FlameLayer.BODY)
            by_event = {command.event_name: command.asset_id for command in plan if command.event_name}
            self.assertEqual(by_event["flame_whiff"], "flame_trail")
            self.assertEqual({command.asset_id for command in plan if command.event_name == "flame_contact"}, {"flame_burst", "ember", "scorch"})
            self.assertEqual(by_event["enemy_fire"], "enemy_fire")

    def test_compositor_is_presentation_only(self) -> None:
        source = (Path(__file__).parents[1] / "src" / "flame_effects.py").read_text(encoding="utf-8")
        self.assertFalse(any(name in source for name in ("health =", "burn_time", "damage =")))


if __name__ == "__main__":
    unittest.main()
