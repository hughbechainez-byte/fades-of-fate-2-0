from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.character_animation import (
    AnimationEvent,
    ClipSpec,
    PlayableCharacterSampler,
    PoseAnchor,
    PoseSpec,
    VfxPlacement,
    VfxSocket,
)


class PlayableAnimationSamplerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_returns_an_immutable_rooted_whole_cel_with_layered_vfx(self) -> None:
        cel = pygame.Surface((16, 16), pygame.SRCALPHA)
        socket = VfxSocket("fist", (11, 7), (1, 0), 3, 9, "front")
        pose = PoseSpec(
            2,
            (8, 15),
            (2, 1, 12, 14),
            (PoseAnchor("head", (8, 2)),),
            (AnimationEvent("contact", 2),),
            (VfxPlacement("trail", socket, "rear_vfx"),),
            (VfxPlacement("shell", socket, "front_vfx"),),
        )
        sampler = PlayableCharacterSampler(
            (ClipSpec("black_dave", "dave_z_01", False, 1, (pose,)),),
            lambda actor, clip, index: cel if (actor, clip, index) == ("black_dave", "dave_z_01", 2) else None,
        )
        sample = sampler.sample("black_dave", "dave_z_01", 0)
        self.assertEqual(sample.root, (8, 15))
        self.assertIs(sample.body_surface, cel)
        self.assertEqual(sample.events[0].name, "contact")
        self.assertEqual(sample.rear_vfx[0].layer, "rear_vfx")
        self.assertEqual(sample.front_vfx[0].layer, "front_vfx")
        with self.assertRaises(AttributeError):
            sample.clip_id = "idle"  # type: ignore[misc]

    def test_missing_registered_clip_or_cel_never_falls_back_to_idle(self) -> None:
        spec = ClipSpec("shelly", "walk", True, 1, (PoseSpec(0, (4, 9), (0, 0, 8, 10)),))
        sampler = PlayableCharacterSampler((spec,), lambda *_: None)
        with self.assertRaisesRegex(ValueError, "unregistered"):
            sampler.sample("shelly", "idle", 0)
        with self.assertRaisesRegex(FileNotFoundError, "missing complete authored cel"):
            sampler.sample("shelly", "walk", 0)

    def test_pose_selection_is_30hz_and_nonlooping_clamps(self) -> None:
        spec = ClipSpec(
            "jermaine", "hurt", False, 2,
            (PoseSpec(4, (8, 15), (0, 0, 16, 16)), PoseSpec(5, (8, 15), (0, 0, 16, 16))),
        )
        sampler = PlayableCharacterSampler((spec,), lambda _a, _c, index: index)
        self.assertEqual(sampler.sample("jermaine", "hurt", 0).pose_index, 4)
        self.assertEqual(sampler.sample("jermaine", "hurt", 2).pose_index, 5)
        self.assertEqual(sampler.sample("jermaine", "hurt", 999).pose_index, 5)


if __name__ == "__main__":
    unittest.main()
