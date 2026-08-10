from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
from PIL import Image

from src import pixel_art, sprite_atlas


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "tools" / "Build-Foundation-Character-Runtime.py"
SPEC = importlib.util.spec_from_file_location("foundation_character_builder", BUILDER_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError(f"could not load {BUILDER_PATH}")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def _rgba_bytes(image: Image.Image) -> bytes:
    return image.convert("RGBA").tobytes()


def _alpha_points(image: Image.Image) -> set[tuple[int, int]]:
    alpha = image.convert("RGBA").getchannel("A")
    return {
        (index % image.width, index // image.width)
        for index, value in enumerate(alpha.get_flattened_data())
        if value
    }


class FoundationCharacterRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_generated_assets_are_current_and_hard_alpha(self) -> None:
        subprocess.run(
            [sys.executable, str(BUILDER_PATH), "--check"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        validation = json.loads(BUILDER.VALIDATION_OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(validation["status"], "PASS")
        self.assertTrue(validation["motion_contract"]["appearance_only_build"])
        self.assertFalse(validation["motion_contract"]["runtime_reorder_performed"])
        self.assertEqual(
            validation["motion_contract"]["source_walk_order"],
            list(BUILDER.WHITE_DAVE_LOCKED_WALK_ORDER),
        )
        for character in ("white_dave", "jermaine"):
            alpha = validation["outputs"][character]["alpha"]
            self.assertEqual(alpha["semitransparent_pixels"], 0)

    def test_white_dave_appearance_pass_cannot_change_motion_pixels(self) -> None:
        with Image.open(BUILDER.WHITE_DAVE_SOURCE) as source_opened:
            source_rows = BUILDER._split_atlas(source_opened.convert("RGBA"))
        with Image.open(BUILDER.WHITE_DAVE_OUTPUT) as output_opened:
            output_rows = BUILDER._split_atlas(output_opened.convert("RGBA"))

        for row, frame_count in enumerate(BUILDER.WHITE_DAVE_ROW_FRAME_COUNTS):
            for column in range(frame_count):
                source = source_rows[row][column]
                output = output_rows[row][column]
                head = BUILDER._head_bounds(source)
                head_bottom = head[3]
                changed = [
                    (x, y)
                    for y in range(BUILDER.CELL_SIZE)
                    for x in range(BUILDER.CELL_SIZE)
                    if source.getpixel((x, y)) != output.getpixel((x, y))
                ]
                self.assertTrue(changed, f"missing appearance pass at {row}:{column}")
                self.assertTrue(
                    all(
                        (head[0] - 2 <= x < head[2] + 2 and head[1] <= y < head[3])
                        or head_bottom + 13 <= y < head_bottom + 30
                        for x, y in changed
                    ),
                    f"appearance edit escaped its mask at {row}:{column}",
                )
                alpha_changes = sum(
                    source.getpixel(point)[3] != output.getpixel(point)[3]
                    for point in changed
                )
                self.assertLessEqual(alpha_changes, 64)
                self.assertEqual(
                    _rgba_bytes(source.crop((0, 90, 128, 128))),
                    _rgba_bytes(output.crop((0, 90, 128, 128))),
                    f"legs or feet changed at {row}:{column}",
                )
                self.assertEqual(
                    source.getchannel("A").getbbox()[3],
                    output.getchannel("A").getbbox()[3],
                    f"ground root changed at {row}:{column}",
                )

    def test_locked_walk_pose_order_is_unchanged(self) -> None:
        with Image.open(BUILDER.WHITE_DAVE_SOURCE) as source_opened:
            source_walk = BUILDER._split_atlas(source_opened.convert("RGBA"))[1]
        with Image.open(BUILDER.WHITE_DAVE_OUTPUT) as output_opened:
            output_walk = BUILDER._split_atlas(output_opened.convert("RGBA"))[1]
        source_masks = [_alpha_points(frame) for frame in source_walk[:12]]
        for index, output in enumerate(output_walk[:12]):
            output_mask = _alpha_points(output)
            scores = [
                len(output_mask & source_mask) / len(output_mask | source_mask)
                for source_mask in source_masks
            ]
            self.assertEqual(max(range(len(scores)), key=scores.__getitem__), index)
            self.assertGreater(scores[index], 0.97)

    def test_jermaine_is_copied_without_visual_edits(self) -> None:
        with Image.open(BUILDER.JERMAINE_SOURCE) as source, Image.open(
            BUILDER.JERMAINE_OUTPUT
        ) as output:
            source_rows = BUILDER._split_atlas(source.convert("RGBA"))
            output_rows = BUILDER._split_atlas(output.convert("RGBA"))
            for row, frame_count in enumerate(BUILDER.JERMAINE_ROW_FRAME_COUNTS):
                for column in range(frame_count):
                    self.assertEqual(
                        _rgba_bytes(source_rows[row][column]),
                        _rgba_bytes(output_rows[row][column]),
                    )
                for column in range(frame_count, BUILDER.RUNTIME_COLUMNS):
                    self.assertIsNone(output_rows[row][column].getchannel("A").getbbox())

    def test_runtime_uses_authored_rows_without_extra_walk_bob(self) -> None:
        white_walk = sprite_atlas.foundation_character_frames("white_dave", "walk")
        jermaine_walk = sprite_atlas.foundation_character_frames("jermaine", "walk")
        self.assertEqual(len(white_walk), 12)
        self.assertEqual(len(jermaine_walk), 8)
        for character, frames in (("white_dave", white_walk), ("jermaine", jermaine_walk)):
            expected_size = round(
                BUILDER.CELL_SIZE * sprite_atlas.FOUNDATION_CHARACTER_RENDER_SCALE[character]
            )
            self.assertTrue(frames)
            self.assertEqual({frame.get_size() for frame in frames}, {(expected_size, expected_size)})
            self.assertEqual(
                sprite_atlas.foundation_character_ground_y(character),
                round(
                    sprite_atlas.FOUNDATION_CHARACTER_GROUND_Y
                    * sprite_atlas.FOUNDATION_CHARACTER_RENDER_SCALE[character]
                ),
            )
        self.assertEqual(
            len({pygame.image.tobytes(frame, "RGBA") for frame in white_walk}),
            12,
        )
        for character in ("white_dave", "jermaine"):
            bottoms = []
            frame_count = len(sprite_atlas.foundation_character_frames(character, "walk"))
            for index in range(frame_count):
                canvas = pygame.Surface((240, 180), pygame.SRCALPHA)
                rect = pixel_art.draw_player(
                    canvas,
                    120,
                    165,
                    0,
                    1,
                    "walk",
                    character,
                    index * 2,
                    (255, 255, 255),
                )
                bottoms.append(rect.bottom)
            self.assertEqual(
                set(bottoms),
                {sprite_atlas.foundation_character_ground_y(character) + 1},
            )
        dave_walk = sprite_atlas.animation_frames("black_dave", "walk")[0]
        self.assertGreaterEqual(
            white_walk[0].get_bounding_rect(min_alpha=1).height,
            round(dave_walk.get_bounding_rect(min_alpha=1).height * 1.03),
        )

    def test_foundation_attacks_receive_no_runtime_motion_overlays(self) -> None:
        canvas = pygame.Surface((240, 180), pygame.SRCALPHA)
        with mock.patch.object(pixel_art, "_draw_action_ribbon") as ribbon, mock.patch.object(
            pixel_art, "_draw_motion_echo"
        ) as echo:
            pixel_art.draw_player(
                canvas,
                120,
                165,
                0,
                1,
                "attack_1",
                "white_dave",
                3,
                (255, 255, 255),
            )
        ribbon.assert_not_called()
        echo.assert_not_called()

    def test_white_dave_menu_portrait_is_native_pixel_art(self) -> None:
        with Image.open(BUILDER.WHITE_DAVE_PORTRAIT) as portrait:
            self.assertEqual(portrait.size, (90, 145))
            self.assertEqual(portrait.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
