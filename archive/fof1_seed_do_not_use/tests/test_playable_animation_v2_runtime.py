from __future__ import annotations

import os
from types import SimpleNamespace
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from src.playable_animation_v2 import PlayableAnimationV2Runtime


class PlayableAnimationV2RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))
        cls.runtime = PlayableAnimationV2Runtime.from_active_resources()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_all_playable_actors_sample_only_registered_rooted_cels(self) -> None:
        for actor in ("black_dave", "shelly", "jermaine", "white_dave"):
            with self.subTest(actor=actor):
                sample = self.runtime.sample(actor, "walk", 3)
                self.assertEqual(sample.actor_id, actor)
                self.assertTrue(sample.body_surface.get_bounding_rect(min_alpha=1).w)
                self.assertGreater(sample.root[0], 0)
                self.assertGreater(sample.root[1], 0)
                with self.assertRaises(ValueError):
                    self.runtime.sample(actor, "unregistered_clip", 0)

    def test_route_execution_selects_its_declared_black_dave_clip(self) -> None:
        execution = SimpleNamespace(
            clip_id="black_dave_v2_regular_04",
            step_id="bdv2_regular_04",
        )
        sample = self.runtime.sample("black_dave", "light", 3, attack_execution=execution)
        self.assertEqual(sample.clip_id, "black_dave_v2_regular_04")

    def test_flame_commands_wrap_the_complete_body_only_when_ignited(self) -> None:
        baseline_canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        self.runtime.draw_actor(
            baseline_canvas,
            actor="black_dave",
            state="black_dave_v2_regular_01",
            authored_tick=3,
            x=250,
            y=286,
            z=0,
            facing=1,
            local_time=0.25,
            flaming=False,
            confirmed_hit=False,
        )
        ignited_canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        self.runtime.draw_actor(
            ignited_canvas,
            actor="black_dave",
            state="black_dave_v2_regular_01",
            authored_tick=3,
            x=250,
            y=286,
            z=0,
            facing=-1,
            local_time=0.25,
            flaming=True,
            confirmed_hit=True,
        )
        self.assertNotEqual(
            pygame.image.tobytes(baseline_canvas, "RGBA"),
            pygame.image.tobytes(ignited_canvas, "RGBA"),
        )
        self.assertEqual(self.runtime.flames.cache.load_count, 1)


if __name__ == "__main__":
    unittest.main()
