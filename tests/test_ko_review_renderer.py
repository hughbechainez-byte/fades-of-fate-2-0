"""Focused deterministic contracts for the KO review GIF renderer."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = PROJECT_ROOT / "tools" / "Render-KO-Review-Gifs.py"
SPEC = importlib.util.spec_from_file_location("ko_review_renderer", TOOL_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError(f"Could not load {TOOL_PATH}")
renderer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = renderer
SPEC.loader.exec_module(renderer)


class KOReviewRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_required_review_gif_contract_is_complete_and_unique(self) -> None:
        self.assertEqual(
            renderer.EXPECTED_GIF_NAMES,
            (
                "skate_right.gif",
                "skate_left.gif",
                "idle_glove_up.gif",
                "target_prep.gif",
                "punch_jab_cross.gif",
                "punch_hook_uppercut.gif",
                "kick_roundhouse.gif",
                "daze_wobble_fall.gif",
                "super_flash_clear.gif",
            ),
        )
        self.assertEqual(len(set(renderer.EXPECTED_GIF_NAMES)), 9)

    def test_thirty_fps_gif_timing_is_deterministic_and_exact_on_average(self) -> None:
        first = renderer._frame_durations(30, 30)
        second = renderer._frame_durations(30, 30)
        self.assertEqual(first, second)
        self.assertEqual(sum(first), 1000)
        self.assertEqual(set(first), {30, 40})
        self.assertTrue(all(duration % 10 == 0 for duration in first))

    def test_shared_palette_no_dither_gif_bytes_and_metadata_are_deterministic(self) -> None:
        frames: list[Image.Image] = []
        for index in range(6):
            frame = Image.new("RGB", renderer.LOGICAL_SIZE, (20, 25, 34))
            draw = ImageDraw.Draw(frame)
            draw.rectangle(
                (40 + index * 17, 100, 130 + index * 17, 250),
                fill=(210 - index * 9, 72 + index * 11, 52 + index * 13),
            )
            draw.line((0, 300 - index, 639, 300 - index), fill=(244, 213, 119), width=2)
            frames.append(frame)
        durations = renderer._frame_durations(len(frames), 30)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.gif"
            second = root / "second.gif"
            renderer._save_gif(frames, first, durations)
            renderer._save_gif(frames, second, durations)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            first_record = renderer._artifact_record(first)
            second_record = renderer._artifact_record(second)
            self.assertEqual(first_record["sha256"], second_record["sha256"])
            self.assertEqual(first_record["width"], 640)
            self.assertEqual(first_record["height"], 360)
            self.assertEqual(first_record["frame_count"], len(frames))
            self.assertEqual(first_record["frame_durations_ms"], durations)
            self.assertEqual(first_record["total_duration_ms"], sum(durations))

    def test_manifest_writer_is_sorted_lf_utf8_and_repeatable(self) -> None:
        payload = {
            "schema_version": 1,
            "logical_size": [640, 360],
            "artifacts": {"skate_right": {"sha256": "0" * 64}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            renderer._write_manifest(first, payload)
            renderer._write_manifest(second, payload)
            raw = first.read_bytes()

            self.assertEqual(raw, second.read_bytes())
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))
            self.assertEqual(json.loads(raw), payload)
            self.assertLess(raw.index(b'"artifacts"'), raw.index(b'"logical_size"'))

    def test_exact_mirror_validator_accepts_one_flip_and_rejects_directionless_art(self) -> None:
        def authored_painter(surface: pygame.Surface, facing: int, tick: int) -> None:
            sprite = pygame.Surface((43, 29), pygame.SRCALPHA)
            pygame.draw.rect(sprite, (225, 112, 67, 255), (2, 5, 17, 20))
            pygame.draw.rect(sprite, (91, 204, 237, 255), (19, 2 + tick % 2, 20, 8))
            if facing < 0:
                sprite = pygame.transform.flip(sprite, True, False)
            surface.blit(sprite, (139, 159))

        result = renderer._validate_exact_mirror(authored_painter, "skate", (0, 1, 2))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["ticks_checked"], 3)

        def directionless_painter(surface: pygame.Surface, facing: int, tick: int) -> None:
            sprite = pygame.Surface((43, 29), pygame.SRCALPHA)
            pygame.draw.rect(sprite, (225, 112, 67, 255), (2, 5, 17, 20))
            pygame.draw.rect(sprite, (91, 204, 237, 255), (19, 2, 20, 8))
            surface.blit(sprite, (139, 159))

        with self.assertRaisesRegex(renderer.ReviewIntegrationError, "not an exact mirror"):
            renderer._validate_exact_mirror(directionless_painter, "skate", (0,))

    def test_bottom_deck_probe_distinguishes_a_board_from_separate_feet(self) -> None:
        skateboard = pygame.Surface((128, 128), pygame.SRCALPHA)
        pygame.draw.rect(skateboard, (210, 145, 52, 255), (39, 116, 50, 2))
        pygame.draw.circle(skateboard, (42, 39, 43, 255), (44, 121), 3)
        pygame.draw.circle(skateboard, (42, 39, 43, 255), (84, 121), 3)

        fighting_stance = pygame.Surface((128, 128), pygame.SRCALPHA)
        pygame.draw.rect(fighting_stance, (42, 39, 43, 255), (26, 116, 12, 8))
        pygame.draw.rect(fighting_stance, (42, 39, 43, 255), (90, 116, 12, 8))

        self.assertEqual(renderer._bottom_horizontal_run(skateboard), 50)
        self.assertEqual(renderer._bottom_horizontal_run(fighting_stance), 12)
        self.assertEqual(renderer._bottom_warm_board_pixels(skateboard), 100)
        self.assertEqual(renderer._bottom_warm_board_pixels(fighting_stance), 0)


if __name__ == "__main__":
    unittest.main()
