"""Strict source, atlas, manifest, and runtime contracts for KO's authored art."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.animation_manifest import (  # noqa: E402
    ANIMATION_CLIPS,
    KO_STATES,
    clip_for,
    total_authored_poses,
)
import src.sprite_atlas as sprite_atlas  # noqa: E402
import src.pixel_art as pixel_art  # noqa: E402


BUILDER_PATH = PROJECT_ROOT / "tools" / "Build-KO-Animation.py"
SPEC = importlib.util.spec_from_file_location("ko_animation_builder", BUILDER_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - importlib guard
    raise RuntimeError(f"could not load KO animation builder: {BUILDER_PATH}")
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


EXPECTED_COUNTS = {
    "idle": 8,
    "skate": 12,
    "prepare": 8,
    "punch_1": 8,
    "punch_2": 8,
    "kick": 8,
    "super": 12,
}
EXPECTED_TOTAL = sum(EXPECTED_COUNTS.values())
CELL_WIDTH = 304
CELL_HEIGHT = 128


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _draw_test_pose(
    draw: ImageDraw.ImageDraw,
    *,
    center_x: int,
    state_index: int,
    pose_index: int,
    clipped: bool = False,
) -> None:
    """Draw one small connected full body with a pose-specific authored mark."""

    if clipped:
        center_x = 6
    outline = (20 + state_index * 4, 28 + pose_index * 3, 40, 255)
    coat = (210, 205 - state_index * 5, 180 + pose_index * 3, 255)
    skin = (128 + state_index * 6, 76 + pose_index * 2, 38, 255)
    glove = (30, 32, 38 + state_index * 5, 255)

    # Head, neck, torso, arms, and legs overlap so every body is one component.
    draw.rectangle((center_x - 4, 5, center_x + 4, 13), fill=skin)
    draw.rectangle((center_x - 2, 12, center_x + 2, 16), fill=skin)
    draw.rectangle((center_x - 7, 15, center_x + 7, 32), fill=coat)
    draw.rectangle((center_x - 10, 17, center_x - 6, 29), fill=coat)
    extension = 10 + (pose_index % 4)
    draw.rectangle((center_x + 6, 17, center_x + extension, 22), fill=coat)
    draw.rectangle((center_x + extension - 2, 19, center_x + extension + 2, 24), fill=glove)
    draw.rectangle((center_x - 7, 30, center_x - 1, 47), fill=outline)
    draw.rectangle((center_x + 1, 30, center_x + 7, 47), fill=outline)
    # A connected color mark makes every cel independently authored even when
    # two silhouettes share the same reach.
    mark = (
        40 + state_index * 20,
        80 + pose_index * 10,
        170 - state_index * 8,
        255,
    )
    draw.rectangle((center_x - 2, 16, center_x + 1, 19), fill=mark)


def _write_test_sources(
    root: Path,
    *,
    duplicate: tuple[str, int] | None = None,
    clipped_state: str | None = None,
    spill_state: str | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    cell_width = 48
    for state_index, state_spec in enumerate(builder.STATE_SPECS):
        source_pose_count = (
            builder.SUPER_BASE_POSE_COUNT
            if state_spec.state == "super"
            else state_spec.pose_count
        )
        image = Image.new(
            "RGBA",
            (cell_width * source_pose_count, 56),
            (*builder.KEY_COLOR, 255),
        )
        draw = ImageDraw.Draw(image)
        for pose_index in range(source_pose_count):
            authored_index = pose_index
            if duplicate == (state_spec.state, pose_index):
                authored_index = 0
            _draw_test_pose(
                draw,
                center_x=pose_index * cell_width + cell_width // 2,
                state_index=state_index,
                pose_index=authored_index,
                clipped=clipped_state == state_spec.state and pose_index == 0,
            )
        if spill_state == state_spec.state:
            draw.point((cell_width - 3, 2), fill=(3, 5, 7, 255))
        image.save(root / state_spec.filename)
    hook = Image.new("RGBA", (cell_width, 56), (*builder.KEY_COLOR, 255))
    _draw_test_pose(
        ImageDraw.Draw(hook),
        center_x=cell_width // 2,
        state_index=6,
        pose_index=12,
    )
    hook.save(root / builder.SUPER_HOOK_FILENAME)


class KOArtContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls) -> None:
        sprite_atlas.clear_cache()
        pygame.quit()

    def tearDown(self) -> None:
        sprite_atlas.clear_cache()

    def _build_fixture(self, temporary: str) -> tuple[Path, Path, dict[str, object]]:
        root = Path(temporary)
        sources = root / "art_source" / "ko"
        atlas = root / "assets" / "sprites" / "ko_animation_atlas.png"
        report = root / "assets" / "sprites" / "ko_animation_validation.json"
        _write_test_sources(sources)
        result = builder.build_ko_animation(
            source_root=sources,
            atlas_output=atlas,
            report_output=report,
            generated_utc="2026-08-04T00:00:00Z",
        )
        return atlas, report, result

    def test_manifest_has_only_the_exact_strict_ko_states(self) -> None:
        self.assertEqual(KO_STATES, tuple(EXPECTED_COUNTS))
        clips = [clip for clip in ANIMATION_CLIPS if clip.actor == "ko"]
        self.assertEqual([clip.state for clip in clips], list(EXPECTED_COUNTS))
        self.assertEqual([clip.frame_count for clip in clips], list(EXPECTED_COUNTS.values()))
        self.assertEqual([clip.row for clip in clips], list(range(7)))
        self.assertTrue(
            all(clip.cell_width == CELL_WIDTH and clip.cell_height == CELL_HEIGHT for clip in clips)
        )
        self.assertTrue(
            all(clip.atlas == "assets/sprites/ko_animation_atlas.png" for clip in clips)
        )
        self.assertEqual(len(ANIMATION_CLIPS), 202)
        self.assertEqual(total_authored_poses(), 1836)
        with self.assertRaisesRegex(ValueError, "unknown KO animation state"):
            clip_for("ko", "recover")

    def test_missing_atlas_fails_closed_without_dave_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing_root = Path(temporary)
            with mock.patch.object(
                sprite_atlas,
                "resource_path",
                side_effect=lambda relative: missing_root / relative,
            ):
                sprite_atlas.clear_cache()
                with self.assertRaisesRegex(FileNotFoundError, "KO authored atlas"):
                    sprite_atlas.ko_frame("idle", 0)
                with self.assertRaisesRegex(FileNotFoundError, "KO authored atlas"):
                    sprite_atlas.player_frame("ko", "idle", 0)
                with self.assertRaisesRegex(ValueError, "unknown KO animation state"):
                    sprite_atlas.ko_frame("walk", 0)

    def test_ko_idle_height_is_strictly_between_dave_and_shelly(self) -> None:
        def tallest(actor: str) -> int:
            return max(
                frame.get_bounding_rect(min_alpha=1).height
                for frame in sprite_atlas.animation_frames(actor, "idle")
            )

        self.assertLess(tallest("shelly"), tallest("ko"))
        self.assertLess(tallest("ko"), tallest("black_dave"))

    def test_builder_rejects_missing_duplicate_clipped_and_spill_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(builder.KOAnimationBuildError, "missing KO source"):
                builder.build_ko_animation(
                    source_root=root / "missing",
                    atlas_output=root / "missing-atlas.png",
                    report_output=root / "missing-report.json",
                )

        cases = (
            ("duplicate", {"duplicate": ("idle", 1)}, "duplicates an earlier"),
            ("clipped", {"clipped_state": "idle"}, "sheet edge.*clipped"),
            ("spill", {"spill_state": "idle"}, "isolated spill component"),
        )
        for label, options, error_pattern in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                sources = root / "sources"
                atlas = root / "atlas.png"
                report = root / "report.json"
                _write_test_sources(sources, **options)
                with self.assertRaisesRegex(builder.KOAnimationBuildError, error_pattern):
                    builder.build_ko_animation(
                        source_root=sources,
                        atlas_output=atlas,
                        report_output=report,
                    )
                self.assertFalse(atlas.exists())
                self.assertFalse(report.exists())

    def test_builder_emits_hard_alpha_grounded_complete_atlas_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atlas_path, report_path, report = self._build_fixture(temporary)
            self.assertTrue(atlas_path.is_file())
            self.assertTrue(report_path.is_file())
            self.assertEqual(report["validation"]["status"], "PASS")
            self.assertEqual(report["validation"]["total_authored_poses"], EXPECTED_TOTAL)
            self.assertEqual(report["validation"]["duplicate_poses"], 0)
            self.assertEqual(report["validation"]["clipped_frames"], 0)
            self.assertFalse(report["validation"]["directional_variants_generated"])
            self.assertEqual(report["output"]["atlas_size_px"], [3648, 896])
            self.assertEqual(report["output"]["cell_size_px"], [CELL_WIDTH, CELL_HEIGHT])
            self.assertEqual(report["output"]["atlas_sha256"], _sha256(atlas_path))
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8"))["output"]["atlas_sha256"],
                _sha256(atlas_path),
            )

            atlas = Image.open(atlas_path).convert("RGBA")
            self.assertEqual(atlas.size, (3648, 896))
            self.assertLessEqual(set(atlas.getchannel("A").get_flattened_data()), {0, 255})
            for row, (state, pose_count) in enumerate(EXPECTED_COUNTS.items()):
                state_report = report["states"][state]
                self.assertEqual(state_report["pose_count"], pose_count)
                expected_segmentation = (
                    "authored_base_plus_single_hook"
                    if state == "super"
                    else "left_to_right_connected_complete_bodies"
                )
                self.assertEqual(state_report["segmentation"]["method"], expected_segmentation)
                self.assertEqual(len(state_report["render"]["frames"]), pose_count)
                self.assertTrue(state_report["render"]["target_height_achieved"])
                self.assertEqual(state_report["render"]["maximum_visible_height_px"], 127)
                self.assertEqual(len(state_report["frame_source_map"]), pose_count)
                if state == "super":
                    self.assertEqual(len(state_report["sources"]), 2)
                    self.assertEqual(
                        state_report["frame_source_map"][6],
                        {
                            "runtime_pose": 7,
                            "source_file": builder.SUPER_HOOK_FILENAME,
                            "source_pose": 1,
                        },
                    )
                for column in range(pose_count):
                    frame = atlas.crop(
                        (
                            column * CELL_WIDTH,
                            row * CELL_HEIGHT,
                            (column + 1) * CELL_WIDTH,
                            (row + 1) * CELL_HEIGHT,
                        )
                    )
                    bounds = frame.getchannel("A").getbbox()
                    self.assertIsNotNone(bounds)
                    self.assertEqual(bounds[3], CELL_HEIGHT)
                    self.assertLessEqual(set(frame.getchannel("A").get_flattened_data()), {0, 255})
                for column in range(pose_count, 12):
                    blank = atlas.crop(
                        (
                            column * CELL_WIDTH,
                            row * CELL_HEIGHT,
                            (column + 1) * CELL_WIDTH,
                            (row + 1) * CELL_HEIGHT,
                        )
                    )
                    self.assertIsNone(blank.getchannel("A").getbbox())

    def test_runtime_selects_exact_ko_cells_without_internal_mirroring(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atlas_path, _, _ = self._build_fixture(temporary)
            root = Path(temporary)
            atlas = pygame.image.load(str(atlas_path))
            with mock.patch.object(
                sprite_atlas,
                "resource_path",
                side_effect=lambda relative: root / relative,
            ):
                sprite_atlas.clear_cache()
                for row, (state, pose_count) in enumerate(EXPECTED_COUNTS.items()):
                    for pose in range(pose_count):
                        with self.subTest(state=state, pose=pose):
                            clip = clip_for("ko", state)
                            tick = pose * clip.hold
                            frame = sprite_atlas.ko_frame(state, tick)
                            expected = atlas.subsurface(
                                (
                                    pose * CELL_WIDTH,
                                    row * CELL_HEIGHT,
                                    CELL_WIDTH,
                                    CELL_HEIGHT,
                                )
                            )
                            self.assertEqual(
                                pygame.image.tobytes(frame, "RGBA"),
                                pygame.image.tobytes(expected, "RGBA"),
                            )
                            self.assertEqual(
                                pygame.image.tobytes(
                                    sprite_atlas.player_frame("ko", state, tick), "RGBA"
                                ),
                                pygame.image.tobytes(expected, "RGBA"),
                            )

    def test_draw_ko_preserves_hard_core_frame_and_mirrors_only_in_renderer(self) -> None:
        authored = pygame.Surface((CELL_WIDTH, CELL_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(authored, (228, 61, 44, 255), (11, 20, 17, 108))
        pygame.draw.rect(authored, (54, 141, 230, 255), (76, 51, 39, 77))
        empty_shadow = pygame.Rect(256, 180, 0, 0)
        with (
            mock.patch.object(sprite_atlas, "ko_frame", return_value=authored) as ko_frame,
            mock.patch.object(pixel_art, "_shadow", return_value=empty_shadow),
            mock.patch.object(
                pixel_art,
                "_draw_ko_super_speed",
                wraps=pixel_art._draw_ko_super_speed,
            ) as speed_wake,
        ):
            right = pygame.Surface((512, 220), pygame.SRCALPHA)
            left = pygame.Surface((512, 220), pygame.SRCALPHA)
            pixel_art.draw_ko(right, 256, 180, facing=1, state="idle", frame=3)
            pixel_art.draw_ko(left, 256, 180, facing=-1, state="idle", frame=3)
            destination = pygame.Rect(104, 52, CELL_WIDTH, CELL_HEIGHT)
            self.assertEqual(
                pygame.image.tobytes(right.subsurface(destination), "RGBA"),
                pygame.image.tobytes(authored, "RGBA"),
            )
            self.assertEqual(
                pygame.image.tobytes(left.subsurface(destination), "RGBA"),
                pygame.image.tobytes(pygame.transform.flip(authored, True, False), "RGBA"),
            )
            self.assertEqual(ko_frame.call_args_list[0], mock.call("idle", 3))
            self.assertEqual(speed_wake.call_count, 0)

    def test_draw_ko_speed_wake_is_super_only_and_missing_art_fails_closed(self) -> None:
        authored = pygame.Surface((CELL_WIDTH, CELL_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(authored, (245, 245, 238, 255), (48, 12, 32, 116))
        canvas = pygame.Surface((640, 240), pygame.SRCALPHA)
        with (
            mock.patch.object(sprite_atlas, "ko_frame", return_value=authored),
            mock.patch.object(
                pixel_art,
                "_draw_ko_super_speed",
                wraps=pixel_art._draw_ko_super_speed,
            ) as speed_wake,
        ):
            for state in ("idle", "skate", "prepare", "punch_1", "punch_2", "kick"):
                pixel_art.draw_ko(canvas, 320, 210, state=state, frame=0)
            self.assertEqual(speed_wake.call_count, 0)
            pixel_art.draw_ko(canvas, 320, 210, state="super", frame=6)
            self.assertEqual(speed_wake.call_count, 1)

        with mock.patch.object(
            sprite_atlas,
            "ko_frame",
            side_effect=FileNotFoundError("authored KO atlas absent"),
        ):
            with self.assertRaisesRegex(FileNotFoundError, "authored KO atlas absent"):
                pixel_art.draw_ko(canvas, 320, 210, state="idle", frame=0)

    def test_repository_atlas_report_matches_every_final_source_hash(self) -> None:
        atlas_path = PROJECT_ROOT / "assets" / "sprites" / "ko_animation_atlas.png"
        report_path = PROJECT_ROOT / "assets" / "sprites" / "ko_animation_validation.json"
        self.assertTrue(atlas_path.is_file(), "final KO atlas has not been built")
        self.assertTrue(report_path.is_file(), "final KO provenance report has not been built")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["validation"]["status"], "PASS")
        self.assertEqual(report["output"]["atlas_sha256"], _sha256(atlas_path))
        self.assertEqual(report["validation"]["total_authored_poses"], EXPECTED_TOTAL)
        for portable_path in (
            report["generator"]["path"],
            report["output"]["atlas_path"],
            report["source_contract"]["root"],
        ):
            self.assertFalse(Path(portable_path).is_absolute())
        for state, state_report in report["states"].items():
            for source in state_report["sources"]:
                source_path = Path(source["path"])
                self.assertFalse(source_path.is_absolute())
                source_path = PROJECT_ROOT / source_path
                self.assertTrue(source_path.is_file(), f"missing {state} source: {source_path}")
                self.assertEqual(source["sha256"], _sha256(source_path))
        super_report = report["states"]["super"]
        self.assertEqual(len(super_report["sources"]), 2)
        self.assertEqual(super_report["frame_source_map"][6]["source_file"], builder.SUPER_HOOK_FILENAME)
        self.assertEqual(
            super_report["segmentation"]["hook_normalization"]["method"],
            "uniform_nearest_to_preceding_authored_pose_height",
        )


if __name__ == "__main__":
    unittest.main()
