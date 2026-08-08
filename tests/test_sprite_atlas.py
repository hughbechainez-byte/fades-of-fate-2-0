"""Asset and state-mapping contracts for the authored pixel-sprite atlases."""

from __future__ import annotations

import os
from pathlib import Path
from statistics import median
import sys
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import resource_path  # noqa: E402
from src.animation_manifest import ANIMATION_CLIPS, clip_for, total_authored_poses  # noqa: E402
from src.entities import ANIMATION_TICKS_PER_SECOND  # noqa: E402
import src.sprite_atlas as sprite_atlas  # noqa: E402
from tools.build_animation_library import (  # noqa: E402
    CHIEF_SOURCES,
    COUCH_SOURCES,
    DAVE_ATTACK_SOURCES,
    DIRECT_RENDER_LIMITS,
    DIRECT_REFERENCE_SPECS,
    DAVE_COMBAT_FIST_LANDMARKS,
    DAVE_ATTACK_FIST_LANDMARKS,
    DAVE_WALK_FIST_LANDMARKS,
    ENEMY_SOURCES,
    HERO_WALK_TORSO_ROOT_X,
    HERO_SOURCES,
    JERRY_SOURCES,
    PROFILES,
    SHELLY_MICROTORCH_ANCHORS,
    SHELLY_EXTRA_SOURCES,
    SHELLY_REFILL_TORCH_ANCHORS,
    PoseTransform,
    _add_shelly_microtorch,
    _canonicalize,
    _profile_for,
    _remove_tiny_alpha_components,
    _remove_distant_walk_ghosts,
    _render_pose,
    _split,
    _split_direct_reference,
    _split_jerry_reference,
    _strip_fit_transform,
)


ATLAS_SPECS = {
    "assets/sprites/black_dave_atlas.png": ((640, 512), (5, 4)),
    "assets/sprites/shelly_atlas.png": ((640, 512), (5, 4)),
    "assets/sprites/chief_atlas.png": ((640, 264), (5, 3)),
    "assets/sprites/enemies_atlas.png": ((800, 512), (5, 4)),
    "assets/sprites/couch_atlas.png": ((800, 288), (5, 2)),
    "assets/sprites/couch_denim_atlas.png": ((640, 256), (5, 2)),
    "assets/sprites/couch_denim_v2_atlas.png": ((640, 256), (5, 2)),
    "assets/sprites/shelly_idle_extras.png": ((512, 256), (4, 2)),
    "assets/sprites/shelly_idle_extended.png": ((1024, 256), (8, 2)),
    "assets/sprites/victory_hug_treats.png": ((1024, 144), (4, 1)),
}

ANIMATION_ATLAS_SPECS = {
    "assets/sprites/black_dave_animation_atlas.png": (1536, 2176),
    "assets/sprites/shelly_animation_atlas.png": (2048, 2176),
    "assets/sprites/chief_animation_atlas.png": (2048, 704),
    "assets/sprites/chief_maul_animation_strip.png": (2048, 128),
    "assets/sprites/enemies_animation_atlas.png": (1920, 4096),
    "assets/sprites/couch_animation_atlas.png": (2048, 1280),
    "assets/sprites/jerry_animation_atlas.png": (2304, 576),
    "assets/sprites/victory_animation_strip.png": (2048, 144),
    "assets/sprites/sunset_bmx_animation_strip.png": (2048, 144),
    "assets/sprites/ko_animation_atlas.png": (3648, 896),
}


def _pixels(surface: pygame.Surface):
    for y in range(surface.get_height()):
        for x in range(surface.get_width()):
            yield surface.get_at((x, y))


def _signature(surface: pygame.Surface | None) -> tuple[tuple[int, int], bytes]:
    if surface is None:
        raise AssertionError("state mapping unexpectedly fell back to procedural art")
    return surface.get_size(), pygame.image.tobytes(surface, "RGBA")


def _translation_normalized_signature(surface: pygame.Surface) -> tuple[tuple[int, int], bytes]:
    bounds = surface.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        raise AssertionError("authored animation pose is empty")
    cropped = surface.subsurface(bounds).copy()
    return cropped.get_size(), pygame.image.tobytes(cropped, "RGBA")


class SpriteAtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        sprite_atlas.clear_cache()

    @classmethod
    def tearDownClass(cls) -> None:
        sprite_atlas.clear_cache()
        pygame.quit()

    def test_atlases_have_expected_dimensions_and_integral_cells(self) -> None:
        for relative, (expected_size, grid) in ATLAS_SPECS.items():
            with self.subTest(atlas=relative):
                path = resource_path(relative)
                self.assertTrue(path.is_file(), f"missing authored atlas: {path}")
                atlas = pygame.image.load(str(path))
                self.assertEqual(atlas.get_size(), expected_size)
                columns, rows = grid
                self.assertEqual(atlas.get_width() % columns, 0)
                self.assertEqual(atlas.get_height() % rows, 0)

        for relative, expected_size in ANIMATION_ATLAS_SPECS.items():
            with self.subTest(animation_atlas=relative):
                path = resource_path(relative)
                self.assertTrue(path.is_file(), f"missing animation library: {path}")
                self.assertEqual(pygame.image.load(str(path)).get_size(), expected_size)

    def test_every_active_animation_uses_meaningful_capture_safe_authored_keys(self) -> None:
        self.assertEqual(len(ANIMATION_CLIPS), 202)
        self.assertEqual(total_authored_poses(), 1836)
        self.assertEqual(ANIMATION_TICKS_PER_SECOND, 30.0)
        for clip in ANIMATION_CLIPS:
            with self.subTest(actor=clip.actor, state=clip.state):
                poses = sprite_atlas.animation_frames(clip.actor, clip.state)
                self.assertEqual(len(poses), clip.frame_count)
                self.assertGreaterEqual(clip.frame_count, 8)
                self.assertEqual(len(set(clip.phases)), clip.frame_count, "animation phases must describe distinct intent")
                raw_signatures = {_signature(pose) for pose in poses}
                normalized_signatures = {_translation_normalized_signature(pose) for pose in poses}
                self.assertEqual(len(raw_signatures), clip.frame_count, "animation contains a repeated drawing")
                self.assertEqual(
                    len(normalized_signatures),
                    clip.frame_count,
                    "animation uses translation-only filler instead of a changed silhouette",
                )

    def test_black_dave_has_dedicated_punch_power_and_shockwave_kick_sources(self) -> None:
        punch_sources = set().union(
            DAVE_ATTACK_SOURCES["attack_1"],
            DAVE_ATTACK_SOURCES["attack_2"],
            DAVE_ATTACK_SOURCES["attack_3"],
        )
        kick_sources = set(DAVE_ATTACK_SOURCES["attack_4"])
        self.assertGreaterEqual(len(punch_sources), 10)
        self.assertTrue({5, 6, 8, 9}.issubset(punch_sources), "uppercut and overhand power cels are required")
        self.assertEqual({12, 13, 14, 15}, kick_sources)
        self.assertEqual(set(range(16)), set(DAVE_ATTACK_FIST_LANDMARKS))

    def test_every_atlas_cell_contains_a_visible_sprite_on_transparency(self) -> None:
        for relative, (_, grid) in ATLAS_SPECS.items():
            atlas = pygame.image.load(str(resource_path(relative)))
            columns, rows = grid
            cell_width = atlas.get_width() // columns
            cell_height = atlas.get_height() // rows
            cell_area = cell_width * cell_height
            for row in range(rows):
                for column in range(columns):
                    with self.subTest(atlas=relative, row=row, column=column):
                        cell = atlas.subsurface(
                            (column * cell_width, row * cell_height, cell_width, cell_height)
                        )
                        visible = sum(pixel.a >= 16 for pixel in _pixels(cell))
                        self.assertGreater(visible, cell_area * 0.02, "sprite cell is empty or nearly empty")
                        self.assertLess(visible, cell_area * 0.85, "sprite cell lost its transparent background")

    def test_black_dave_attack_frames_keep_transparency_and_stable_bounds(self) -> None:
        for state in ("attack_1", "attack_2", "attack_3", "attack_4"):
            with self.subTest(state=state):
                frames = sprite_atlas.animation_frames("black_dave", state)
                bounds = [frame.get_bounding_rect(min_alpha=16) for frame in frames]
                visible_pixels = [
                    sum(1 for y in range(frame.get_height()) for x in range(frame.get_width()) if frame.get_at((x, y)).a >= 16)
                    for frame in frames
                ]
                cell_area = frames[0].get_width() * frames[0].get_height()
                for visible in visible_pixels:
                    transparent_fraction = 1.0 - visible / cell_area
                    self.assertLess(visible / cell_area, 0.90, "attack frame became too opaque")
                    self.assertGreater(transparent_fraction, 0.10, "attack frame lost substantial matte transparency")
                widths = [entry.w for entry in bounds]
                heights = [entry.h for entry in bounds]
                bottoms = [entry.bottom for entry in bounds]
                tops = [entry.top for entry in bounds]
                self.assertLessEqual(max(widths), frames[0].get_width(), "attack source bounds left frame edges")
                self.assertLessEqual(max(widths) - min(widths), 120, "attack bounds are drifting by too much")
                self.assertLessEqual(max(heights) - min(heights), 40, "attack bounds are drifting by too much")
                self.assertLessEqual(max(bottoms) - min(bottoms), 2, "attack baseline shifted between attack frames")
                self.assertLessEqual(max(tops), 40, "attack upper bound moved above the grounded baseline contract")

    def test_no_visible_hot_magenta_chroma_key_residue(self) -> None:
        for relative in ATLAS_SPECS:
            atlas = pygame.image.load(str(resource_path(relative)))
            residue = sum(
                pixel.a >= 8 and pixel.r >= 210 and pixel.b >= 210 and pixel.g <= 90
                for pixel in _pixels(atlas)
            )
            with self.subTest(atlas=relative):
                self.assertEqual(residue, 0, "visible #ff00ff-style chroma residue remains")

    def test_hero_and_chief_state_mappings_are_visually_distinct(self) -> None:
        for character in ("black_dave", "shelly"):
            with self.subTest(character=character):
                signatures = {
                    tuple(_signature(frame) for frame in sprite_atlas.animation_frames(character, state))
                    for state in ("idle", "walk", "light", "heavy", "hurt", "super")
                }
                self.assertEqual(len(signatures), 6)

        breathing = _signature(sprite_atlas.player_frame("shelly", "idle", 0))
        butane_refill = _signature(
            sprite_atlas.player_frame("shelly", "idle", sprite_atlas.SHELLY_REFILL_WINDOW[0])
        )
        pants_pull = _signature(
            sprite_atlas.player_frame("shelly", "idle", sprite_atlas.SHELLY_PANTS_WINDOW[0])
        )
        petting = _signature(sprite_atlas.player_frame("shelly", "pet", 0))
        self.assertEqual(len({breathing, butane_refill, pants_pull, petting}), 4)
        refill_signatures = {
            _signature(sprite_atlas.player_frame("shelly", "refill", tick))
            for tick in range(96)
        }
        pants_signatures = {
            _signature(sprite_atlas.player_frame("shelly", "pants", tick))
            for tick in range(96)
        }
        breath_signatures = {
            _signature(frame) for frame in sprite_atlas.animation_frames("shelly", "idle")
        }
        refill_count = sum(
            _signature(sprite_atlas.player_frame("shelly", "idle", tick)) in refill_signatures
            for tick in range(sprite_atlas.SHELLY_IDLE_CYCLE_TICKS)
        )
        pants_count = sum(
            _signature(sprite_atlas.player_frame("shelly", "idle", tick)) in pants_signatures
            for tick in range(sprite_atlas.SHELLY_IDLE_CYCLE_TICKS)
        )
        breathing_count = sum(
            _signature(sprite_atlas.player_frame("shelly", "idle", tick)) in breath_signatures
            for tick in range(sprite_atlas.SHELLY_IDLE_CYCLE_TICKS)
        )
        self.assertEqual(refill_count, sprite_atlas.SHELLY_REFILL_WINDOW[1] - sprite_atlas.SHELLY_REFILL_WINDOW[0])
        self.assertEqual(pants_count, sprite_atlas.SHELLY_PANTS_WINDOW[1] - sprite_atlas.SHELLY_PANTS_WINDOW[0])
        self.assertGreaterEqual(
            breathing_count,
            sprite_atlas.SHELLY_IDLE_CYCLE_TICKS
            - (sprite_atlas.SHELLY_REFILL_WINDOW[1] - sprite_atlas.SHELLY_REFILL_WINDOW[0])
            - (sprite_atlas.SHELLY_PANTS_WINDOW[1] - sprite_atlas.SHELLY_PANTS_WINDOW[0]),
            "subtle breathing must remain Shelly's default idle",
        )

        extended_refill = {
            _signature(sprite_atlas.player_frame("shelly", "refill", tick))
            for tick in range(120)
        }
        extended_pants = {
            _signature(sprite_atlas.player_frame("shelly", "pants_pull", tick))
            for tick in range(120)
        }
        self.assertEqual(len(extended_refill), 16)
        self.assertEqual(len(extended_pants), 16)

        chief_signatures = {
            tuple(_signature(frame) for frame in sprite_atlas.animation_frames("chief", state))
            for state in ("idle", "run", "attack", "guard", "pet", "sit")
        }
        self.assertEqual(len(chief_signatures), 6)

    def test_hero_stride_phases_and_planted_breathing_are_cohesive(self) -> None:
        base_stride = (
            "left_heel_strike",
            "left_weight_accept",
            "left_mid_stance",
            "right_leg_passing",
            "left_heel_rise",
            "left_toe_off",
            "right_heel_strike",
            "right_weight_accept",
            "right_mid_stance",
            "left_leg_passing",
            "right_heel_rise",
            "right_toe_off",
        )
        for character in ("black_dave", "shelly"):
            with self.subTest(character=character):
                self.assertEqual(clip_for(character, "walk").phases, base_stride)
                self.assertEqual(len(sprite_atlas.animation_frames(character, "walk")), 12)
                idle = sprite_atlas.animation_frames(character, "idle")
                self.assertEqual(len(idle), 12)
                foot_lines = {
                    bounds.bottom
                    for frame in idle
                    if (bounds := frame.get_bounding_rect(min_alpha=1)).height
                }
                self.assertEqual(len(foot_lines), 1, "breathing must not slide or lift planted feet")
                reference = pygame.mask.from_surface(idle[0])
                overlap_scores = []
                for frame in idle[1:]:
                    mask = pygame.mask.from_surface(frame)
                    intersection = reference.overlap_area(mask, (0, 0))
                    union = reference.count() + mask.count() - intersection
                    overlap_scores.append(intersection / max(1, union))
                self.assertGreater(min(overlap_scores), 0.84, "idle changed pose instead of breathing subtly")

    def test_hero_stride_and_combat_keep_proportions_stable(self) -> None:
        """Regression coverage for the warped/shrinking hero rendering bug."""

        for character in ("black_dave", "shelly"):
            with self.subTest(character=character, motion="stride_cadence"):
                self.assertEqual(clip_for(character, "walk").hold, 2)

            for state in (
                "attack_1", "attack_2", "attack_3", "attack_4", "heavy",
                "ranged", "dodge", "hurt", "super", "air_attack", "jump", "pet",
            ):
                with self.subTest(character=character, action=state):
                    profile = PROFILES[_profile_for(character, state)]
                    self.assertTrue(
                        all(
                            transform.angle == 0.0
                            and transform.scale_x == transform.scale_y
                            for transform in profile
                        ),
                        "active hero poses must use a uniform, unrotated pixel scale",
                    )

        dave_heights = [
            frame.get_bounding_rect(min_alpha=1).height
            for state in ("idle", "walk")
            for frame in sprite_atlas.animation_frames("black_dave", state)
        ]
        shelly_heights = [
            frame.get_bounding_rect(min_alpha=1).height
            for state in ("idle", "walk")
            for frame in sprite_atlas.animation_frames("shelly", state)
        ]
        self.assertGreaterEqual(
            min(dave_heights),
            max(shelly_heights) + 3,
            "Dave must remain visibly taller than Shelly in standing/stride silhouettes",
        )

    def test_true_stride_keys_have_even_motion_without_synthetic_sawtooth(self) -> None:
        def changed_fraction(first: pygame.Surface, second: pygame.Surface) -> float:
            changed = sum(
                first.get_at((x, y)) != second.get_at((x, y))
                for y in range(first.get_height())
                for x in range(first.get_width())
            )
            return changed / (first.get_width() * first.get_height())

        for character in ("black_dave", "shelly"):
            with self.subTest(character=character):
                frames = sprite_atlas.animation_frames(character, "walk")
                deltas = [
                    changed_fraction(frame, frames[(index + 1) % len(frames)])
                    for index, frame in enumerate(frames)
                ]
                self.assertGreater(min(deltas), 0.25, "a near-duplicate gait cel recreates the small half of the old sawtooth")
                self.assertLess(
                    max(deltas) / min(deltas),
                    1.75,
                    "adjacent authored gait changes are uneven enough to recreate large/small snapping",
                )

    def test_walk_strips_use_one_scale_and_preserve_authored_pose_compression(self) -> None:
        reference_root = resource_path("assets/reference")
        for character, filename in (
            ("black_dave", "black_dave_walk_reference_v2.png"),
            ("shelly", "shelly_walk_reference_v2.png"),
        ):
            with self.subTest(character=character):
                sources = [_remove_distant_walk_ghosts(frame) for frame in _split(reference_root / filename, 6, 2)]
                indices = HERO_SOURCES["walk"]
                clip = clip_for(character, "walk")
                transform = _strip_fit_transform(
                    sources,
                    indices,
                    (clip.cell_width, clip.cell_height),
                )
                rendered = [
                    _render_pose(
                        sources[source_index],
                        transform,
                        (clip.cell_width, clip.cell_height),
                        source_root_x=HERO_WALK_TORSO_ROOT_X[character][source_index],
                    )
                    for source_index in indices
                ]
                source_heights = [
                    bounds[3] - bounds[1]
                    for source_index in indices
                    if (bounds := sources[source_index].getchannel("A").getbbox()) is not None
                ]
                rendered_heights = [
                    bounds[3] - bounds[1]
                    for frame in rendered
                    if (bounds := frame.getchannel("A").getbbox()) is not None
                ]
                self.assertEqual(len(source_heights), len(rendered_heights))
                source_max = max(source_heights)
                rendered_max = max(rendered_heights)
                for source_height, rendered_height in zip(source_heights, rendered_heights):
                    self.assertAlmostEqual(
                        rendered_height / rendered_max,
                        source_height / source_max,
                        delta=0.015,
                        msg="per-frame fitting changed the actor's apparent body scale",
                    )
                self.assertGreater(
                    max(rendered_heights) - min(rendered_heights),
                    3,
                    "authored knee compression was flattened by independent frame fitting",
                )

    def test_hero_walk_roots_are_stable_without_edge_ghosts(self) -> None:
        """A world-moving actor cannot also inherit concept-sheet translation."""

        def upper_body_axis(frame: pygame.Surface) -> float:
            bounds = frame.get_bounding_rect(min_alpha=1)
            self.assertTrue(bounds.w and bounds.h)
            start = bounds.top + round(bounds.h * 0.26)
            end = bounds.top + round(bounds.h * 0.55)
            xs = [
                x
                for y in range(start, end)
                for x in range(bounds.left, bounds.right)
                if frame.get_at((x, y)).a >= 64
            ]
            self.assertTrue(xs)
            return float(median(xs))

        for character in ("black_dave", "shelly"):
            with self.subTest(character=character):
                frames = sprite_atlas.animation_frames(character, "walk")
                axes = [upper_body_axis(frame) for frame in frames]
                foot_lines = {frame.get_bounding_rect(min_alpha=1).bottom for frame in frames}
                self.assertLessEqual(
                    max(axes) - min(axes),
                    3.0,
                    "upper torso is inheriting a concept-sheet translation instead of a stable walk root",
                )
                self.assertEqual(foot_lines, {frames[0].get_bounding_rect(min_alpha=1).bottom})

        stable_timeline = [sprite_atlas.player_frame("black_dave", "walk", tick) for tick in range(24)]
        self.assertTrue(all(frame is not None for frame in stable_timeline))
        stable_signatures = [_signature(frame) for frame in stable_timeline]
        self.assertEqual(len(set(stable_signatures)), 12, "Dave must use twelve stable gait poses")
        expected_counts = {pose: 3 if pose in {0, 5, 6, 11} else 2 if pose in {1, 2, 7, 8} else 1 for pose in range(12)}
        observed_counts = {pose: 0 for pose in range(12)}
        pose_signatures: list[bytes] = []
        stable_frames: list[pygame.Surface] = []
        for signature in stable_signatures:
            if signature not in pose_signatures:
                pose_signatures.append(signature)
                stable_frames.append(stable_timeline[stable_signatures.index(signature)])
        for signature in stable_signatures:
            observed_counts[pose_signatures.index(signature)] += 1
        self.assertEqual(observed_counts, expected_counts, "Dave's weighted cadence must favor contact and toe-off beats")
        stable_bounds = [frame.get_bounding_rect(min_alpha=1) for frame in stable_frames]
        self.assertEqual({bounds.bottom for bounds in stable_bounds}, {stable_bounds[0].bottom})
        for phase in range(6):
            first = stable_bounds[phase]
            opposite = stable_bounds[phase + 6]
            self.assertLessEqual(abs(first.w - opposite.w), 10)
            self.assertLessEqual(abs(first.top - opposite.top), 3)
        locked_palette = {
            tuple(frame.get_at((x, y)))[:3]
            for frame in stable_frames
            for y in range(frame.get_height())
            for x in range(frame.get_width())
            if frame.get_at((x, y)).a >= 128
        }
        self.assertEqual(len(locked_palette), 192, "Dave's walk must use the approved identity palette")
        self.assertEqual(
            _signature(sprite_atlas.player_frame("black_dave", "walk", 0)),
            _signature(sprite_atlas.player_frame("black_dave", "walk", 24)),
            "the 12-pose, 24-tick gait must loop without a timing seam",
        )

        raw_dave = _split(resource_path("assets/reference/black_dave_walk_reference_v2.png"), 6, 2)
        for phase in (1, 9):
            with self.subTest(dave_phase=phase):
                raw_alpha = raw_dave[phase].getchannel("A")
                cleaned_alpha = _remove_distant_walk_ghosts(raw_dave[phase]).getchannel("A")
                edge_pixels_before = sum(
                    raw_alpha.getpixel((x, y)) >= 8
                    for y in range(raw_alpha.height)
                    for x in (*range(10), *range(raw_alpha.width - 10, raw_alpha.width))
                )
                edge_pixels_after = sum(
                    cleaned_alpha.getpixel((x, y)) >= 8
                    for y in range(cleaned_alpha.height)
                    for x in (*range(10), *range(cleaned_alpha.width - 10, cleaned_alpha.width))
                )
                self.assertGreater(edge_pixels_before, 0, "fixture no longer exercises the detached render spill")
                self.assertEqual(edge_pixels_after, 0, "distant walk-sheet ghost survived into the runtime strip")

    def test_pose_builder_registers_asymmetric_silhouettes_to_the_source_root(self) -> None:
        def source_with_reach(left: int, right: int) -> Image.Image:
            source = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(source)
            draw.rectangle((28, 18, 36, 59), fill=(120, 82, 55, 255))
            draw.rectangle((left, 25, right, 31), fill=(150, 96, 63, 255))
            draw.rectangle((31, 57, 33, 60), fill=(255, 0, 0, 255))
            return source

        rendered = [
            _render_pose(source_with_reach(4, 33), PoseTransform(), (64, 64)),
            _render_pose(source_with_reach(31, 60), PoseTransform(), (64, 64)),
        ]
        root_centres = []
        for pose in rendered:
            roots = [
                (x, y)
                for y in range(pose.height)
                for x in range(pose.width)
                if (lambda pixel: pixel[0] > 240 and pixel[1] < 10 and pixel[2] < 10 and pixel[3] > 240)(pose.getpixel((x, y)))
            ]
            root_centres.append((sum(x for x, _ in roots) / len(roots), max(y for _, y in roots)))
        self.assertEqual(root_centres[0], root_centres[1])
        self.assertAlmostEqual(root_centres[0][0], 32.0, delta=1.0)

    def test_dave_fist_anchors_follow_the_selected_authored_pose(self) -> None:
        cell_size, metadata = sprite_atlas._load_dave_fist_metadata()
        dave_clips = tuple(clip for clip in ANIMATION_CLIPS if clip.actor == "black_dave")
        self.assertEqual(cell_size, (128, 128))
        self.assertEqual(set(metadata), {clip.state for clip in dave_clips})
        self.assertEqual(sum(len(phases) for phases in metadata.values()), 144)

        for clip in dave_clips:
            state = clip.state
            for phase in range(clip.frame_count):
                with self.subTest(state=state, phase=phase):
                    tick = phase * clip.hold
                    frame = sprite_atlas.player_frame("black_dave", state, tick)
                    assert frame is not None
                    anchors = sprite_atlas.player_fist_anchors("black_dave", state, tick)
                    self.assertEqual(len(anchors), 2)
                    self.assertNotEqual(anchors[0], anchors[1])
                    expected = tuple(
                        (
                            round((point[0] + 0.5) * frame.get_width() / cell_size[0] - 0.5),
                            round((point[1] + 0.5) * frame.get_height() / cell_size[1] - 0.5),
                        )
                        for point in metadata[state][phase]
                    )
                    self.assertEqual(anchors, expected)
                    for x, y in anchors:
                        self.assertTrue(0 <= x < frame.get_width() and 0 <= y < frame.get_height())
                        # The semantic centre may lie on knuckle outline or a
                        # wrist band. It must nevertheless remain physically
                        # adjacent to authored hand pixels after every rotate,
                        # crop and 128->143 runtime scale.
                        nearby_skin = any(
                            sprite_atlas._is_dave_skin(frame.get_at((sample_x, sample_y)))
                            for sample_y in range(max(0, y - 10), min(frame.get_height(), y + 11))
                            for sample_x in range(max(0, x - 10), min(frame.get_width(), x + 11))
                        )
                        self.assertTrue(nearby_skin)

        # Golden semantic checks cover every previously observed anatomy
        # confusion class. These are deliberately independent of the skin
        # predicate: the old shoe/bicep points also looked "skin colored".
        semantic_goldens = {
            ("idle", 4): ((50, 48), (85, 49)),
            ("walk", 1): ((57, 76), (94, 76)),
            ("attack_1", 2): ((46, 28), (96, 26)),
            ("attack_3", 4): ((54, 59), (91, 32)),
            ("heavy", 4): ((39, 62), (93, 30)),
            ("hurt", 4): ((39, 62), (93, 30)),
            ("down", 6): ((83, 98), (93, 129)),
            ("down", 7): ((82, 102), (91, 131)),
            ("pet", 2): ((51, 54), (82, 47)),
            ("refill", 3): ((62, 82), (82, 37)),
            ("pants", 6): ((53, 62), (83, 55)),
            ("super", 4): ((51, 43), (97, 37)),
        }
        for (state, phase), expected in semantic_goldens.items():
            with self.subTest(golden=f"{state}:{phase}"):
                self.assertEqual(sprite_atlas._dave_fist_anchors(state, phase), expected)

        self.assertLess(sprite_atlas._dave_fist_anchors("idle", 4)[1][0], 90, "idle lead flame returned to Dave's bicep")
        for state in ("attack_3", "heavy", "hurt", "air_attack", "jump"):
            kick_phase = 4 if state != "air_attack" else 3
            lead = sprite_atlas._dave_fist_anchors(state, kick_phase)[1]
            self.assertLess(lead[0], 110, f"{state} lead flame returned to the raised sneaker")

        self.assertEqual(sprite_atlas.player_fist_anchors("shelly", "walk", 0), ())
        self.assertEqual(
            sprite_atlas.player_fist_anchors("dave", "light", 4),
            sprite_atlas.player_fist_anchors("black_dave", "attack_1", 4),
        )
        lead_positions = {
            sprite_atlas.player_fist_anchors("black_dave", "attack_1", phase)[1]
            for phase in range(8)
        }
        self.assertGreaterEqual(len(lead_positions), 5, "flames would remain fixed while Dave changes pose")

    def test_dave_fist_metadata_fallback_is_bounded_and_avoids_color_extremes(self) -> None:
        for clip in (candidate for candidate in ANIMATION_CLIPS if candidate.actor == "black_dave"):
            for phase, frame in enumerate(sprite_atlas.animation_frames("black_dave", clip.state)):
                with self.subTest(state=clip.state, phase=phase):
                    anchors = sprite_atlas._fallback_dave_fist_anchors(frame, clip.state)
                    self.assertEqual(len(anchors), 2)
                    self.assertNotEqual(anchors[0], anchors[1])
                    for point in anchors:
                        self.assertTrue(frame.get_rect().collidepoint(point))
        kick_frame = sprite_atlas.animation_frames("black_dave", "heavy")[4]
        self.assertLess(
            sprite_atlas._fallback_dave_fist_anchors(kick_frame, "heavy")[1][0],
            120,
            "metadata fallback selected the pale raised sneaker",
        )

    def test_expanded_nonhero_idle_and_locomotion_families_are_single_source_and_planted(self) -> None:
        expected_counts = {
            ("chief", "idle"): 12,
            ("chief", "move"): 12,
            ("chief", "sit"): 16,
            ("couch", "idle"): 12,
            ("couch", "walk"): 16,
            **{(kind, state): 12 for kind in ("stick", "cart", "whip", "pipe") for state in ("idle", "walk")},
            **{("jerry", state): 12 for state in ("idle", "support", "talk", "point")},
        }
        for (actor, state), frame_count in expected_counts.items():
            with self.subTest(actor=actor, state=state):
                clip = clip_for(actor, state)
                frames = sprite_atlas.animation_frames(actor, state)
                self.assertEqual(clip.frame_count, frame_count)
                self.assertEqual(len(frames), frame_count)
                foot_lines = {
                    bounds.bottom
                    for frame in frames
                    if (bounds := frame.get_bounding_rect(min_alpha=1)).height
                }
                self.assertLessEqual(
                    max(foot_lines) - min(foot_lines),
                    1,
                    "expanded loop drifts more than one scaled pixel from its ground line",
                )

        def raw_atlas_frames(actor: str, state: str) -> tuple[pygame.Surface, ...]:
            clip = clip_for(actor, state)
            siblings = [candidate for candidate in ANIMATION_CLIPS if candidate.atlas == clip.atlas]
            columns = max(candidate.frame_count for candidate in siblings)
            rows = max(candidate.row for candidate in siblings) + 1
            atlas = pygame.image.load(str(resource_path(clip.atlas)))
            cell_width = atlas.get_width() // columns
            cell_height = atlas.get_height() // rows
            return tuple(
                atlas.subsurface(
                    (phase * cell_width, clip.row * cell_height, cell_width, cell_height)
                ).copy()
                for phase in range(clip.frame_count)
            )

        reference_root = resource_path("assets/reference")
        for (actor, state), (filename, columns, rows) in DIRECT_REFERENCE_SPECS.items():
            with self.subTest(direct_reference=f"{actor}:{state}"):
                clip = clip_for(actor, state)
                sources = _split_direct_reference(reference_root / filename, columns, rows)
                actual = raw_atlas_frames(actor, state)
                self.assertEqual(len(sources), clip.frame_count)
                transform = _strip_fit_transform(
                    sources,
                    tuple(range(len(sources))),
                    (clip.cell_width, clip.cell_height),
                    DIRECT_RENDER_LIMITS.get((actor, state)),
                )
                for phase, source in enumerate(sources):
                    frame = actual[phase]
                    expected = _render_pose(
                        source,
                        transform,
                        (clip.cell_width, clip.cell_height),
                        DIRECT_RENDER_LIMITS.get((actor, state)),
                    )
                    self.assertEqual(
                        pygame.image.tobytes(frame, "RGBA"),
                        expected.tobytes(),
                        f"direct key phase {phase} changed during atlas build",
                    )

        sprite_root = resource_path("assets/sprites")
        source_sets = {
            "chief": _split(sprite_root / "chief_atlas.png", 5, 3),
            "enemies": _canonicalize(_split(sprite_root / "enemies_atlas.png", 5, 4), {8, 18}),
            "couch": [
                _remove_tiny_alpha_components(frame)
                for frame in _canonicalize(_split(sprite_root / "couch_denim_v2_atlas.png", 5, 2), {6, 7})
            ],
            "jerry": _split_jerry_reference(reference_root / "jerry_pose_reference_v2.png"),
        }
        indirect_states = [
            ("chief", "idle", source_sets["chief"], CHIEF_SOURCES["idle"]),
            *[
                (
                    kind,
                    "idle",
                    source_sets["enemies"],
                    tuple(kind_index * 5 + source for source in ENEMY_SOURCES["idle"]),
                )
                for kind_index, kind in enumerate(("stick", "cart", "whip", "pipe"))
            ],
            ("couch", "idle", source_sets["couch"], COUCH_SOURCES["idle"]),
            *[("jerry", state, source_sets["jerry"], JERRY_SOURCES[state]) for state in ("idle", "support", "talk", "point")],
        ]
        for actor, state, sources, indices in indirect_states:
            with self.subTest(single_source=f"{actor}:{state}"):
                clip = clip_for(actor, state)
                profile = PROFILES[_profile_for(actor, state)]
                actual = raw_atlas_frames(actor, state)
                self.assertEqual(len(indices), clip.frame_count)
                self.assertEqual(len(profile), len(indices))
                for phase, (source_index, transform) in enumerate(zip(indices, profile)):
                    frame = actual[phase]
                    expected = _render_pose(
                        sources[source_index],
                        transform,
                        (clip.cell_width, clip.cell_height),
                    )
                    self.assertEqual(
                        pygame.image.tobytes(frame, "RGBA"),
                        expected.tobytes(),
                        f"expanded phase {phase} gained a second anatomy/prop layer",
                    )

    def test_every_shelly_non_idle_cell_has_one_anatomy_source_and_keeps_fire(self) -> None:
        sprite_root = resource_path("assets/sprites")
        reference_root = resource_path("assets/reference")
        base_sources = [
            _add_shelly_microtorch(frame, SHELLY_MICROTORCH_ANCHORS[index])
            for index, frame in enumerate(_split(sprite_root / "shelly_atlas.png", 5, 4))
        ]
        extra_sources = [
            _add_shelly_microtorch(frame, SHELLY_REFILL_TORCH_ANCHORS[index])
            if index < len(SHELLY_REFILL_TORCH_ANCHORS) else frame
            for index, frame in enumerate(_split(sprite_root / "shelly_idle_extended.png", 8, 2))
        ]
        walk_sources = [
            _remove_distant_walk_ghosts(frame)
            for frame in _split(reference_root / "shelly_walk_reference_v2.png", 6, 2)
        ]

        for clip in (clip for clip in ANIMATION_CLIPS if clip.actor == "shelly" and clip.state != "idle"):
            with self.subTest(state=clip.state):
                if clip.state == "walk":
                    sources = walk_sources
                    indices = HERO_SOURCES[clip.state]
                    transform = _strip_fit_transform(
                        sources,
                        indices,
                        (clip.cell_width, clip.cell_height),
                    )
                    profile = (transform,) * len(indices)
                elif clip.state in {"refill", "pants"}:
                    sources = extra_sources
                    indices = SHELLY_EXTRA_SOURCES[clip.state]
                    profile = PROFILES[_profile_for(clip.actor, clip.state)]
                else:
                    sources = base_sources
                    indices = HERO_SOURCES[clip.state]
                    profile = PROFILES[_profile_for(clip.actor, clip.state)]
                    if profile[-1] == profile[0]:
                        profile = (*profile[:-1], PoseTransform(0.9, 1.01, 0.99, 1, 0))

                actual = sprite_atlas.animation_frames("shelly", clip.state)
                self.assertEqual(len(indices), len(actual))
                self.assertEqual(len(profile), len(indices))
                for phase, (source_index, transform) in enumerate(zip(indices, profile)):
                    frame = actual[phase]
                    expected = _render_pose(
                        sources[source_index],
                        transform,
                        (clip.cell_width, clip.cell_height),
                        source_root_x=(
                            HERO_WALK_TORSO_ROOT_X["shelly"][source_index]
                            if clip.state == "walk"
                            else None
                        ),
                    )
                    self.assertEqual(
                        pygame.image.tobytes(frame, "RGBA"),
                        expected.tobytes(),
                        f"phase {phase} gained a second anatomy layer after its single source render",
                    )

        def fire_pixels(frame: pygame.Surface) -> int:
            return sum(
                pixel.a and pixel.r > 230 and 105 < pixel.g < 235 and pixel.b < 65 and pixel.r - pixel.g > 30
                for pixel in _pixels(frame)
            )

        self.assertLessEqual(
            max(fire_pixels(frame) for frame in sprite_atlas.animation_frames("shelly", "walk")),
            2,
            "locomotion reference unexpectedly contains a detached flame/arm-like effect",
        )
        for state in ("attack_1", "attack_2", "attack_3", "attack_4", "heavy", "ranged", "super", "air_attack"):
            with self.subTest(fire_effect=state):
                self.assertGreater(
                    max(fire_pixels(frame) for frame in sprite_atlas.animation_frames("shelly", state)),
                    20,
                    "torch/fire effect was lost while removing duplicate anatomy",
                )

    def test_every_animation_family_has_crisp_motion_subframes(self) -> None:
        samples = (
            lambda tick: sprite_atlas.player_frame("black_dave", "idle", tick),
            lambda tick: sprite_atlas.player_frame("black_dave", "light", tick),
            lambda tick: sprite_atlas.player_frame("shelly", "walk", tick),
            lambda tick: sprite_atlas.chief_frame("sit", tick),
            lambda tick: sprite_atlas.chief_frame("attack", tick),
            lambda tick: sprite_atlas.enemy_frame("stick", "walk", tick),
            lambda tick: sprite_atlas.enemy_frame("pipe", "attack", tick),
            lambda tick: sprite_atlas.boss_frame("idle", tick),
            lambda tick: sprite_atlas.boss_frame("walk", tick),
            lambda tick: sprite_atlas.boss_frame("pump_attack", tick),
        )
        for index, sample in enumerate(samples):
            with self.subTest(animation=index):
                signatures = {_signature(sample(tick)) for tick in range(60)}
                self.assertGreaterEqual(len(signatures), 8)

    def test_victory_strip_has_hug_and_treat_sequence_frames(self) -> None:
        signatures = {_signature(sprite_atlas.victory_frame(index)) for index in range(8)}
        self.assertEqual(len(signatures), 8)

    def test_jerry_has_detailed_walker_dialogue_and_direction_poses(self) -> None:
        state_signatures = {
            tuple(_signature(frame) for frame in sprite_atlas.animation_frames("jerry", state))
            for state in ("idle", "support", "talk", "point")
        }
        self.assertEqual(len(state_signatures), 4)
        self.assertEqual(
            _signature(sprite_atlas.jerry_frame("warn", 0)),
            _signature(sprite_atlas.jerry_frame("talk", 0)),
        )
        self.assertEqual(
            _signature(sprite_atlas.jerry_frame("direction", 24)),
            _signature(sprite_atlas.jerry_frame("point", 24)),
        )
        point_pose = sprite_atlas.jerry_frame("point", 24)
        self.assertIsNotNone(point_pose)
        visible_pixels = [pixel for pixel in _pixels(point_pose) if pixel.a >= 16]
        self.assertGreater(sum(pixel.r < 55 and pixel.g < 55 and pixel.b < 55 for pixel in visible_pixels), 350)
        self.assertGreater(sum(abs(pixel.r - pixel.g) < 24 and pixel.r > 105 for pixel in visible_pixels), 120)

    def test_sunset_bmx_strip_has_eight_detailed_group_cels(self) -> None:
        frames = tuple(sprite_atlas.sunset_frame(index) for index in range(8))
        self.assertEqual(len({_signature(frame) for frame in frames}), 8)
        for index, frame in enumerate(frames):
            with self.subTest(frame=index):
                self.assertIsNotNone(frame)
                visible_pixels = [pixel for pixel in _pixels(frame) if pixel.a >= 16]
                self.assertGreater(len(visible_pixels), 3_500)
                self.assertGreater(
                    sum(pixel.b > pixel.r * 1.25 and pixel.b > pixel.g * 1.08 for pixel in visible_pixels),
                    180,
                    "BMX frame lost the blue bike/denim/cargo visual detail",
                )

    def test_one_shot_actions_hold_their_final_pose_instead_of_looping(self) -> None:
        samples = (
            (lambda tick: sprite_atlas.player_frame("black_dave", "attack_1", tick), 15),
            (lambda tick: sprite_atlas.chief_frame("attack", tick), 15),
            (lambda tick: sprite_atlas.enemy_frame("pipe", "attack", tick), 15),
            (lambda tick: sprite_atlas.boss_frame("attack", tick), 15),
        )
        for index, (sample, final_tick) in enumerate(samples):
            with self.subTest(animation=index):
                self.assertNotEqual(_signature(sample(0)), _signature(sample(final_tick)))
                self.assertEqual(_signature(sample(final_tick)), _signature(sample(99)))

        self.assertNotEqual(
            _signature(sprite_atlas.enemy_frame("stick", "recovery", 0)),
            _signature(sprite_atlas.enemy_frame("stick", "walk", 0)),
        )

    def test_enemy_archetypes_and_combat_states_are_visually_distinct(self) -> None:
        idle_signatures = set()
        for kind in ("stick", "cart", "whip", "pipe"):
            with self.subTest(kind=kind):
                signatures = {
                    tuple(_signature(frame) for frame in sprite_atlas.animation_frames(kind, state))
                    for state in ("idle", "walk", "attack", "hurt")
                }
                self.assertEqual(len(signatures), 4)
                idle_signatures.add(_signature(sprite_atlas.enemy_frame(kind, "idle", 0)))
        self.assertEqual(len(idle_signatures), 4)

    def test_unknown_enemy_kind_is_rejected_instead_of_falling_back(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown enemy kind"):
            sprite_atlas.enemy_frame("prototype_enemy", "idle", 0)

    def test_couch_personality_and_combat_states_are_visually_distinct(self) -> None:
        signatures = {
            tuple(_signature(frame) for frame in sprite_atlas.animation_frames("couch", state))
            for state in ("idle", "laugh", "walk", "attack", "pump_attack", "hurt")
        }
        self.assertEqual(len(signatures), 6)


if __name__ == "__main__":
    unittest.main()
