from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
from PIL import Image

from src import animation_manifest, pixel_art, sprite_atlas
from src.config import resource_path
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_IDS = (
    "encampment_bottle_scarf",
    "encampment_bottle_puffer",
    "encampment_tire_slinger",
    "underpass_tire_runner",
    "cart_tent_bottle_pitcher",
    "mall_security_watch",
    "event_security_heavy",
    "night_security_patrol",
    "city_patrol_nightstick",
    "transit_patrol_nightstick",
    "riot_line_nightstick",
    "bike_patrol_taser",
    "tactical_taser_unit",
)
PROJECTILE_STYLES = frozenset({"glass_bottle", "bike_tire", "taser"})
DROPPED_TIRE_VARIANTS = frozenset(
    {"encampment_tire_slinger", "underpass_tire_runner"}
)
LEGACY_ENEMY_ATLAS = "assets/sprites/enemies_animation_atlas.png"
CELL_TRANSPARENT_INSET = 2


def _load_preview_tool():
    path = PROJECT_ROOT / "tools" / "Build-Enemy-Roster-Previews.py"
    spec = importlib.util.spec_from_file_location("enemy_roster_preview_tool", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load preview tool: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_art_builder():
    path = PROJECT_ROOT / "tools" / "Build-Enemy-Roster-Art.py"
    spec = importlib.util.spec_from_file_location("enemy_roster_art_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load art builder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_animation_builder():
    path = PROJECT_ROOT / "tools" / "build_animation_library.py"
    spec = importlib.util.spec_from_file_location("enemy_roster_animation_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load animation builder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _pose_tick(clip: animation_manifest.AnimationClip, phase_index: int) -> int:
    return phase_index * max(1, int(clip.hold))


def _cropped_signature(frame: pygame.Surface) -> bytes:
    bounds = frame.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        raise AssertionError("dedicated enemy cel is empty")
    cropped = frame.subsurface(bounds).copy()
    return pygame.image.tobytes(cropped, "RGBA")


def _point_distance(left: tuple[int, int], right: tuple[int, int]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _material_detail(frame: pygame.Surface) -> tuple[int, int]:
    visible = 0
    colors: set[tuple[int, int, int]] = set()
    for y in range(frame.get_height()):
        for x in range(frame.get_width()):
            pixel = frame.get_at((x, y))
            if pixel.a < 16:
                continue
            visible += 1
            colors.add((pixel.r, pixel.g, pixel.b))
    return visible, len(colors)


def _component_contains_point(
    component: pygame.Mask,
    point: tuple[int, int],
    *,
    radius: int = 3,
) -> bool:
    for y in range(max(0, point[1] - radius), min(component.get_size()[1], point[1] + radius + 1)):
        for x in range(max(0, point[0] - radius), min(component.get_size()[0], point[0] + radius + 1)):
            if component.get_at((x, y)):
                return True
    return False


def _point_near_visible_alpha(
    frame: pygame.Surface,
    point: tuple[int, int],
    *,
    radius: int = 4,
) -> bool:
    for y in range(max(0, point[1] - radius), min(frame.get_height(), point[1] + radius + 1)):
        for x in range(max(0, point[0] - radius), min(frame.get_width(), point[0] + radius + 1)):
            if frame.get_at((x, y)).a >= 16:
                return True
    return False


def _magenta_edge_pixels(frame: pygame.Surface) -> int:
    residue = 0
    width, height = frame.get_size()
    for y in range(height):
        for x in range(width):
            pixel = frame.get_at((x, y))
            if not pixel.a:
                continue
            if not (
                pixel.r >= 120
                and pixel.b >= 100
                and pixel.g * 2 < min(pixel.r, pixel.b)
                and abs(pixel.r - pixel.b) <= 80
            ):
                continue
            if any(
                0 <= x + dx < width
                and 0 <= y + dy < height
                and frame.get_at((x + dx, y + dy)).a == 0
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                residue += 1
    return residue


def _neon_family(pixel: pygame.Color) -> str | None:
    if pixel.a < 16:
        return None
    if pixel.g >= 220 and pixel.g >= pixel.r + 90 and pixel.g >= pixel.b + 90:
        return "green"
    if (
        pixel.g >= 210
        and pixel.b >= 210
        and pixel.r <= 100
        and min(pixel.g, pixel.b) >= pixel.r + 100
    ):
        return "cyan"
    if (
        pixel.r >= 210
        and pixel.b >= 175
        and pixel.g <= 110
        and min(pixel.r, pixel.b) >= pixel.g + 90
    ):
        return "magenta"
    return None


def _marker_like_neon_crosses(frame: pygame.Surface) -> list[tuple[int, int]]:
    """Find tiny colored plus marks without rejecting broad material accents."""

    hits: list[tuple[int, int]] = []
    width, height = frame.get_size()
    for y in range(2, height - 2):
        for x in range(2, width - 2):
            family = _neon_family(frame.get_at((x, y)))
            if family is None:
                continue
            for arm in (1, 2):
                cardinal = (
                    (x - arm, y),
                    (x + arm, y),
                    (x, y - arm),
                    (x, y + arm),
                )
                if not all(_neon_family(frame.get_at(point)) == family for point in cardinal):
                    continue
                diagonals = (
                    (x - arm, y - arm),
                    (x + arm, y - arm),
                    (x - arm, y + arm),
                    (x + arm, y + arm),
                )
                if sum(_neon_family(frame.get_at(point)) == family for point in diagonals) <= 1:
                    hits.append((x, y))
                    break
    return hits


class EnemyRosterArtContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))
        sprite_atlas.clear_cache()
        cls.manager = InputManager(max_players=4, discover_controllers=False)
        cls.game = FadesGame(cls.manager, mute=True)
        cls.game.select_slots = [
            SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
        ]
        cls.game._start_stage()
        cls.human = next(player for player in cls.game.players if not player.is_cpu)
        for player in cls.game.players:
            if player is not cls.human:
                player.state = "eliminated"
        cls.catalog = cls.game.enemy_variant_catalog
        cls.preview = _load_preview_tool()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.game.close()
        cls.manager.close()
        sprite_atlas.clear_cache()
        pygame.quit()

    def _kind(self, variant_id: str) -> str:
        return str(self.catalog[variant_id]["runtime_kind"])

    def test_each_model_has_dedicated_manifest_actor_atlas_and_pose_provenance(self) -> None:
        mapping = animation_manifest.ENEMY_VARIANT_ANIMATION_ACTORS
        self.assertTrue(set(MODEL_IDS).issubset(mapping))
        actors: dict[str, str] = {}
        actor_atlases: dict[str, str] = {}

        for variant_id in MODEL_IDS:
            kind = self._kind(variant_id)
            actor = animation_manifest.enemy_animation_actor(kind, variant_id)
            actors[variant_id] = actor
            self.assertEqual(actor, mapping[variant_id])
            self.assertNotIn(actor, animation_manifest.ENEMY_KINDS)
            atlases: set[str] = set()

            for state in animation_manifest.ENEMY_STATES:
                clip = animation_manifest.clip_for(actor, state)
                self.assertEqual(clip.actor, actor)
                self.assertEqual(clip.state, state)
                self.assertGreater(clip.frame_count, 0)
                frames = sprite_atlas.animation_frames(actor, state)
                self.assertEqual(len(frames), clip.frame_count)
                atlases.add(clip.atlas)
                self.assertTrue(Path(resource_path(clip.atlas)).is_file())
                self.assertNotEqual(clip.atlas, LEGACY_ENEMY_ATLAS)

                for phase_index, expected_frame in enumerate(frames):
                    tick = _pose_tick(clip, phase_index)
                    runtime_frame = sprite_atlas.enemy_frame(
                        kind,
                        state,
                        tick,
                        variant_id=variant_id,
                    )
                    self.assertIsNotNone(runtime_frame)
                    assert runtime_frame is not None
                    self.assertEqual(
                        pygame.image.tobytes(runtime_frame, "RGBA"),
                        pygame.image.tobytes(expected_frame, "RGBA"),
                    )
                    metadata = sprite_atlas.enemy_pose_anchors(
                        kind,
                        state,
                        tick,
                        variant_id=variant_id,
                    )
                    self.assertTrue(str(metadata.get("source_key", "")).strip())

            self.assertEqual(len(atlases), 1, f"{variant_id} is split across atlas sources")
            actor_atlases[actor] = next(iter(atlases))

        self.assertEqual(len(set(actors.values())), len(MODEL_IDS))
        self.assertEqual(len(set(actor_atlases.values())), len(MODEL_IDS))

    def test_art_rebuild_uses_tracked_sources_and_exact_authored_landmarks(self) -> None:
        builder = _load_art_builder()
        landmarks_path = Path(builder.AUTHORED_LANDMARKS_PATH)
        metadata_path = PROJECT_ROOT / "assets" / "sprites" / "enemies" / "enemy_variant_source_anchors.json"
        landmarks = json.loads(landmarks_path.read_text(encoding="utf-8"))
        checked_in_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(set(landmarks["actors"]), set(MODEL_IDS))
        self.assertEqual(set(checked_in_metadata["actors"]), set(MODEL_IDS))
        self.assertEqual(
            checked_in_metadata["landmark_source"],
            landmarks_path.relative_to(PROJECT_ROOT).as_posix(),
        )

        for variant_id in MODEL_IDS:
            expected_keys = landmarks["actors"][variant_id]["source_keys"]
            actual_actor = checked_in_metadata["actors"][variant_id]
            self.assertEqual(actual_actor["source_keys"], expected_keys)
            reference = str(actual_actor["reference"])
            self.assertTrue(reference.startswith("art_source/enemy_roster/"))
            self.assertNotIn("build/", reference)
            reference_path = PROJECT_ROOT / reference
            self.assertTrue(reference_path.is_file())
            self.assertEqual(
                hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                actual_actor["reference_sha256"],
            )
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", reference],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
            )
            self.assertNotEqual(ignored.returncode, 0, f"authored source is ignored: {reference}")

        builder_source = (PROJECT_ROOT / "tools" / "Build-Enemy-Roster-Art.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(builder_source)
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        pending = ["_source_metadata"]
        visited: set[str] = set()
        forbidden: list[str] = []
        while pending:
            function_name = pending.pop()
            if function_name in visited:
                continue
            visited.add(function_name)
            function = functions[function_name]
            for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
                if isinstance(call.func, ast.Name):
                    name = call.func.id
                    if name in {"_nearest_alpha", "_weapon_anchor"}:
                        forbidden.append(name)
                    if name in functions and name not in visited:
                        pending.append(name)
                elif isinstance(call.func, ast.Attribute) and call.func.attr == "centroid":
                    forbidden.append("centroid")
        self.assertEqual(
            forbidden,
            [],
            "landmark generation derives coordinates instead of copying the reviewed table",
        )

        build_dir = PROJECT_ROOT / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="enemy-roster-contract-", dir=build_dir) as temp_name:
            temporary_root = Path(temp_name)
            rebuilt = builder.build(
                temporary_root,
                PROJECT_ROOT / "art_source" / "enemy_roster",
                landmarks_path,
                temporary_root / "clean-contact.png",
                temporary_root / "anchor-qa.png",
            )
            self.assertEqual(rebuilt, checked_in_metadata)
            for variant_id in MODEL_IDS:
                relative = checked_in_metadata["actors"][variant_id]["source_atlas"]
                self.assertEqual(
                    hashlib.sha256((temporary_root / relative).read_bytes()).hexdigest(),
                    hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest(),
                    f"{variant_id} source atlas does not rebuild deterministically",
                )

    def test_runtime_phases_rebuild_from_declared_whole_cel_transforms(self) -> None:
        builder = _load_animation_builder()
        source_metadata_path = (
            PROJECT_ROOT
            / "assets"
            / "sprites"
            / "enemies"
            / "enemy_variant_source_anchors.json"
        )
        runtime_metadata_path = (
            PROJECT_ROOT
            / "assets"
            / "sprites"
            / "enemies"
            / "enemy_variant_anchors.json"
        )
        source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
        runtime_metadata = json.loads(runtime_metadata_path.read_text(encoding="utf-8"))
        cell_width, cell_height = (int(value) for value in source_metadata["cell_size"])
        self.assertEqual((cell_width, cell_height), (160, 128))
        self.assertEqual(set(runtime_metadata["actors"]), set(MODEL_IDS))

        for variant_id in MODEL_IDS:
            kind = self._kind(variant_id)
            actor = animation_manifest.enemy_animation_actor(kind, variant_id)
            source_actor = source_metadata["actors"][variant_id]
            runtime_actor = runtime_metadata["actors"][variant_id]
            self.assertEqual(runtime_actor["source_atlas"], source_actor["source_atlas"])
            source_atlas = Image.open(resource_path(source_actor["source_atlas"])).convert("RGBA")

            for state in animation_manifest.ENEMY_STATES:
                clip = animation_manifest.clip_for(actor, state)
                phases = runtime_actor["states"][state]
                runtime_frames = sprite_atlas.animation_frames(actor, state)
                self.assertEqual(len(phases), clip.frame_count)
                self.assertEqual(len(runtime_frames), clip.frame_count)

                for phase_index, (phase_metadata, runtime_frame) in enumerate(
                    zip(phases, runtime_frames, strict=True)
                ):
                    source_key = str(phase_metadata["source_key"])
                    self.assertIn(source_key, source_actor["source_keys"])
                    source_phase = source_actor["source_keys"][source_key]
                    source_index = int(phase_metadata["source_index"])
                    self.assertEqual(source_index, int(source_phase["index"]))
                    self.assertEqual(int(phase_metadata["phase_index"]), phase_index)
                    profile_id = builder.ENEMY_VARIANT_TRANSFORM_PROFILE_IDS[state]
                    override_key = (variant_id, state, phase_index)
                    expected_transform = builder.ENEMY_VARIANT_TRANSFORM_PROFILES[state][
                        phase_index
                    ]
                    if override_key in builder.ENEMY_VARIANT_ACTOR_TRANSFORM_OVERRIDES:
                        profile_id = f"{profile_id}:actor_override_v1"
                        expected_transform = (
                            builder.ENEMY_VARIANT_ACTOR_TRANSFORM_OVERRIDES[override_key]
                        )
                    self.assertEqual(phase_metadata["transform_profile"], profile_id)

                    transform_payload = phase_metadata["transform"]
                    transform = builder.PoseTransform(
                        angle=float(transform_payload["angle"]),
                        scale_x=float(transform_payload["scale_x"]),
                        scale_y=float(transform_payload["scale_y"]),
                        offset_x=int(transform_payload["offset_x"]),
                        offset_y=int(transform_payload["offset_y"]),
                    )
                    self.assertEqual(
                        transform,
                        expected_transform,
                    )
                    source_frame = source_atlas.crop(
                        (
                            source_index * cell_width,
                            0,
                            (source_index + 1) * cell_width,
                            cell_height,
                        )
                    )
                    rebuilt_frame, rebuilt_anchors, ground_offset_y = (
                        builder._render_enemy_variant_pose(
                            source_frame,
                            transform,
                            source_phase,
                        )
                    )
                    with self.subTest(
                        variant=variant_id,
                        state=state,
                        phase=phase_index,
                        source_key=source_key,
                    ):
                        self.assertEqual(
                            int(transform_payload["ground_offset_y"]),
                            ground_offset_y,
                        )
                        for field in (
                            "root",
                            "rear_hand",
                            "lead_hand",
                            "weapon_anchor",
                            "release_anchor",
                        ):
                            self.assertEqual(phase_metadata[field], rebuilt_anchors[field])
                        for field in ("held_gear", "gear_state", "component_count"):
                            self.assertEqual(phase_metadata[field], source_phase[field])
                        self.assertEqual(
                            pygame.image.tobytes(runtime_frame, "RGBA"),
                            rebuilt_frame.tobytes(),
                            "runtime phase differs from its declared whole-cel transform",
                        )

                        if source_key == "down":
                            source_bounds = source_frame.getchannel("A").getbbox()
                            rebuilt_bounds = rebuilt_frame.getchannel("A").getbbox()
                            self.assertIsNotNone(source_bounds)
                            self.assertIsNotNone(rebuilt_bounds)
                            assert source_bounds is not None and rebuilt_bounds is not None
                            source_ratio = (
                                (source_bounds[2] - source_bounds[0])
                                / (source_bounds[3] - source_bounds[1])
                            )
                            rebuilt_ratio = (
                                (rebuilt_bounds[2] - rebuilt_bounds[0])
                                / (rebuilt_bounds[3] - rebuilt_bounds[1])
                            )
                            self.assertGreater(source_ratio, 1.5)
                            self.assertGreater(rebuilt_ratio, 1.45)
                            self.assertGreaterEqual(rebuilt_ratio, source_ratio * 0.65)
                            self.assertLessEqual(abs(transform.angle), 0.5)
                            self.assertTrue(0.99 <= transform.scale_x <= 1.01)
                            self.assertTrue(0.99 <= transform.scale_y <= 1.01)
                            self.assertEqual(rebuilt_anchors["root"], [80, 118])

                        if variant_id in DROPPED_TIRE_VARIANTS and source_key == "down":
                            self.assertEqual(phase_metadata["gear_state"], "dropped")
                            self.assertFalse(phase_metadata["held_gear"])
                            self.assertEqual(int(phase_metadata["component_count"]), 2)
                            runtime_components = sorted(
                                [
                                    component
                                    for component in pygame.mask.from_surface(
                                        runtime_frame,
                                        threshold=7,
                                    ).connected_components(3)
                                    if component.count() >= 20
                                ],
                                key=lambda component: component.count(),
                                reverse=True,
                            )
                            self.assertEqual(len(runtime_components), 2)
                            runtime_weapon = phase_metadata["weapon_anchor"]
                            self.assertIsInstance(runtime_weapon, list)
                            assert isinstance(runtime_weapon, list)
                            self.assertTrue(
                                _component_contains_point(
                                    runtime_components[1],
                                    (int(runtime_weapon[0]), int(runtime_weapon[1])),
                                ),
                                "transformed dropped tire anchor does not identify detached gear",
                            )

        build_dir = PROJECT_ROOT / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="enemy-roster-animation-contract-",
            dir=build_dir,
        ) as temp_name:
            temporary_root = Path(temp_name)
            builder._make_atlases(temporary_root, enemy_roster_only=True)
            rebuilt_metadata_path = (
                temporary_root
                / "assets"
                / "sprites"
                / "enemies"
                / "enemy_variant_anchors.json"
            )
            self.assertEqual(
                rebuilt_metadata_path.read_bytes(),
                runtime_metadata_path.read_bytes(),
                "declared transformed landmark metadata is not deterministic",
            )
            for variant_id in MODEL_IDS:
                relative = runtime_metadata["actors"][variant_id]["atlas"]
                self.assertEqual(
                    hashlib.sha256((temporary_root / relative).read_bytes()).hexdigest(),
                    hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest(),
                    f"{variant_id} runtime atlas does not rebuild deterministically",
                )

    def test_dedicated_models_bypass_legacy_enemy_overlay_compositors(self) -> None:
        surface = pygame.Surface((400, 240), pygame.SRCALPHA)
        with (
            mock.patch.object(
                pixel_art,
                "_legacy_encampment_variant_frame",
                side_effect=AssertionError("legacy homeless overlay was invoked"),
            ),
            mock.patch.object(
                pixel_art,
                "_security_uniform_frame",
                side_effect=AssertionError("legacy uniform overlay was invoked"),
            ),
        ):
            for variant_id in MODEL_IDS:
                kind = self._kind(variant_id)
                with self.subTest(variant=variant_id):
                    surface.fill((0, 0, 0, 0))
                    rendered = pixel_art.draw_enemy(
                        surface,
                        200,
                        200,
                        facing=1,
                        state="attack",
                        kind=f"{kind}:{variant_id}",
                        frame=0,
                    )
                    self.assertGreater(rendered.w, 0)
                    self.assertGreater(rendered.h, 0)

    def test_authored_gear_states_match_visible_component_semantics(self) -> None:
        metadata_path = (
            PROJECT_ROOT
            / "assets"
            / "sprites"
            / "enemies"
            / "enemy_variant_source_anchors.json"
        )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        cell_width, cell_height = (int(value) for value in metadata["cell_size"])

        for variant_id in MODEL_IDS:
            actor_metadata = metadata["actors"][variant_id]
            source_atlas = pygame.image.load(
                resource_path(actor_metadata["source_atlas"])
            ).convert_alpha()
            for source_key, source_metadata in actor_metadata["source_keys"].items():
                source_index = int(source_metadata["index"])
                frame = source_atlas.subsurface(
                    pygame.Rect(
                        source_index * cell_width,
                        0,
                        cell_width,
                        cell_height,
                    )
                )
                components = sorted(
                    [
                        component
                        for component in pygame.mask.from_surface(
                            frame,
                            threshold=7,
                        ).connected_components(3)
                        if component.count() >= 20
                    ],
                    key=lambda component: component.count(),
                    reverse=True,
                )
                self.assertTrue(components)
                state = str(source_metadata["gear_state"])
                held = bool(source_metadata["held_gear"])
                raw_anchor = source_metadata["weapon_anchor"]
                anchor = (
                    None
                    if raw_anchor is None
                    else (int(raw_anchor[0]), int(raw_anchor[1]))
                )
                with self.subTest(
                    variant=variant_id,
                    source_key=source_key,
                    gear_state=state,
                ):
                    if variant_id in DROPPED_TIRE_VARIANTS and source_key == "down":
                        self.assertEqual(state, "dropped")
                    if state in {"absent", "released"}:
                        self.assertFalse(held)
                        self.assertIsNone(
                            anchor,
                            f"{state} gear invents a visible weapon anchor",
                        )
                    elif state == "dropped":
                        self.assertFalse(held)
                        self.assertIsNotNone(anchor)
                        assert anchor is not None
                        self.assertGreaterEqual(
                            len(components),
                            2,
                            "dropped gear is not detached from the body silhouette",
                        )
                        self.assertEqual(
                            len(components),
                            2,
                            "dropped gear must be exactly body plus one detached prop",
                        )
                        self.assertEqual(int(source_metadata["component_count"]), 2)
                        self.assertTrue(
                            any(
                                _component_contains_point(component, anchor)
                                for component in components[1:]
                            ),
                            "dropped weapon anchor does not identify a non-body gear component",
                        )
                    elif state == "held":
                        self.assertTrue(held)
                        self.assertIsNotNone(anchor)
                        assert anchor is not None
                        self.assertTrue(
                            any(
                                _component_contains_point(component, anchor)
                                for component in components
                            ),
                            "held weapon anchor was snapped away from visible gear",
                        )
                    else:
                        self.fail(f"unsupported gear_state: {state!r}")

    def test_material_detail_and_scale_track_the_pre_tent_complete_enemy_reference(self) -> None:
        reference = sprite_atlas.animation_frames("stick", "idle")[0]
        reference_bounds = reference.get_bounding_rect(min_alpha=16)
        reference_visible, reference_colors = _material_detail(reference)

        for variant_id in MODEL_IDS:
            kind = self._kind(variant_id)
            actor = animation_manifest.enemy_animation_actor(kind, variant_id)
            frame = sprite_atlas.animation_frames(actor, "idle")[0]
            bounds = frame.get_bounding_rect(min_alpha=16)
            visible, colors = _material_detail(frame)
            with self.subTest(variant=variant_id):
                self.assertGreaterEqual(bounds.h, round(reference_bounds.h * 0.78))
                self.assertGreaterEqual(visible, round(reference_visible * 0.45))
                self.assertGreaterEqual(
                    colors,
                    round(reference_colors * 0.20),
                    "model fell back to flat placeholder materials instead of the established detailed style",
                )

    def test_every_cel_clears_cell_edges_and_keeps_a_registered_ground_root(self) -> None:
        for variant_id in MODEL_IDS:
            kind = self._kind(variant_id)
            actor = animation_manifest.enemy_animation_actor(kind, variant_id)
            rendered_bottoms: list[int] = []
            bottom_offsets: list[int] = []

            for state in animation_manifest.ENEMY_STATES:
                clip = animation_manifest.clip_for(actor, state)
                for phase_index, frame in enumerate(sprite_atlas.animation_frames(actor, state)):
                    tick = _pose_tick(clip, phase_index)
                    with self.subTest(variant=variant_id, state=state, phase=phase_index):
                        width, height = frame.get_size()
                        alpha = pygame.mask.from_surface(frame)
                        self.assertGreater(alpha.count(), 0)
                        for inset in range(CELL_TRANSPARENT_INSET):
                            self.assertFalse(any(frame.get_at((x, inset)).a for x in range(width)))
                            self.assertFalse(
                                any(frame.get_at((x, height - 1 - inset)).a for x in range(width))
                            )
                            self.assertFalse(any(frame.get_at((inset, y)).a for y in range(height)))
                            self.assertFalse(
                                any(frame.get_at((width - 1 - inset, y)).a for y in range(height))
                            )

                        root = sprite_atlas.enemy_root_anchor(
                            kind,
                            state,
                            tick,
                            variant_id=variant_id,
                        )
                        self.assertIsNotNone(root)
                        assert root is not None
                        self.assertTrue(0 <= root[0] < width)
                        self.assertTrue(0 <= root[1] < height)
                        bounds = frame.get_bounding_rect(min_alpha=1)
                        bottom_offsets.append(bounds.bottom - root[1])
                        floor_gap = root[1] - (bounds.bottom - 1)
                        self.assertGreaterEqual(floor_gap, 0, "root rose above visible floor pixels")
                        self.assertLessEqual(floor_gap, 4, "root is detached below the visible floor")

                        for facing in (-1, 1):
                            surface = pygame.Surface((400, 240), pygame.SRCALPHA)
                            rendered = pixel_art.draw_enemy(
                                surface,
                                200,
                                200,
                                facing=facing,
                                state=state,
                                kind=f"{kind}:{variant_id}",
                                frame=tick,
                            )
                            if facing > 0:
                                expected_bounds = bounds
                                registered_x = root[0]
                            else:
                                expected_bounds = pygame.transform.flip(frame, True, False).get_bounding_rect(
                                    min_alpha=1
                                )
                                registered_x = width - 1 - root[0]
                            expected = expected_bounds.move(200 - registered_x, 200 - root[1])
                            self.assertEqual(rendered, expected)
                            rendered_bottoms.append(rendered.bottom)

            self.assertLessEqual(max(bottom_offsets) - min(bottom_offsets), 1)
            self.assertLessEqual(max(rendered_bottoms) - min(rendered_bottoms), 1)
            self.assertLessEqual(abs(round(sum(rendered_bottoms) / len(rendered_bottoms)) - 200), 1)

    def test_cels_have_no_neighbor_fragments_or_chroma_key_fringe(self) -> None:
        reference = sprite_atlas.animation_frames("stick", "idle")[0]
        self.assertEqual(_magenta_edge_pixels(reference), 0)

        for variant_id in MODEL_IDS:
            kind = self._kind(variant_id)
            actor = animation_manifest.enemy_animation_actor(kind, variant_id)
            for state in animation_manifest.ENEMY_STATES:
                clip = animation_manifest.clip_for(actor, state)
                for phase_index, frame in enumerate(sprite_atlas.animation_frames(actor, state)):
                    tick = _pose_tick(clip, phase_index)
                    metadata = sprite_atlas.enemy_pose_anchors(
                        kind,
                        state,
                        tick,
                        variant_id=variant_id,
                    )
                    components = sorted(
                        pygame.mask.from_surface(frame, 0).connected_components(),
                        key=lambda component: component.count(),
                        reverse=True,
                    )
                    with self.subTest(variant=variant_id, state=state, phase=phase_index):
                        self.assertTrue(components)
                        for field in ("rear_hand", "lead_hand"):
                            hand = metadata.get(field)
                            self.assertIsInstance(hand, tuple)
                            assert isinstance(hand, tuple)
                            self.assertTrue(
                                _point_near_visible_alpha(frame, hand),
                                f"{field} anchor misses the authored hand pixels",
                            )
                        allowed = {id(components[0])}
                        weapon_anchor = metadata.get("weapon_anchor")
                        if isinstance(weapon_anchor, tuple):
                            self.assertTrue(
                                _point_near_visible_alpha(frame, weapon_anchor),
                                "weapon anchor misses visible held/dropped gear pixels",
                            )
                            gear_components = [
                                component
                                for component in components
                                if _component_contains_point(component, weapon_anchor)
                            ]
                            self.assertTrue(gear_components)
                            allowed.update(id(component) for component in gear_components)
                        if metadata.get("held_gear"):
                            self.assertIsInstance(
                                weapon_anchor,
                                tuple,
                                "held gear has no authored anchor in the exact runtime cel",
                            )
                        unexpected = [
                            component.count()
                            for component in components
                            if id(component) not in allowed
                        ]
                        self.assertEqual(
                            unexpected,
                            [],
                            "cel contains a detached neighbor/body fragment with no authored gear anchor",
                        )
                        self.assertEqual(
                            _magenta_edge_pixels(frame),
                            0,
                            "cel retains chroma-key fringe absent from the established enemy atlas",
                        )
                        self.assertEqual(
                            _marker_like_neon_crosses(frame),
                            [],
                            "cel contains a tiny neon plus/spark marker baked into production art",
                        )

    def test_complete_authored_cels_have_meaningful_state_and_actor_signatures(self) -> None:
        actor_signatures: dict[str, str] = {}
        for variant_id in MODEL_IDS:
            kind = self._kind(variant_id)
            actor = animation_manifest.enemy_animation_actor(kind, variant_id)
            state_signatures: dict[str, str] = {}
            actor_digest = hashlib.sha256()

            for state in animation_manifest.ENEMY_STATES:
                state_digest = hashlib.sha256()
                phase_signatures: list[tuple[tuple[int, int], bytes]] = []
                for frame in sprite_atlas.animation_frames(actor, state):
                    signature = _cropped_signature(frame)
                    phase_signatures.append(
                        (frame.get_bounding_rect(min_alpha=1).size, signature)
                    )
                    state_digest.update(len(signature).to_bytes(8, "little"))
                    state_digest.update(signature)
                self.assertEqual(
                    len(set(phase_signatures)),
                    len(phase_signatures),
                    f"{variant_id}:{state} repeats a translated or held source drawing",
                )
                state_signatures[state] = state_digest.hexdigest()
                actor_digest.update(state.encode("utf-8"))
                actor_digest.update(state_digest.digest())

            self.assertEqual(
                len(set(state_signatures.values())),
                len(animation_manifest.ENEMY_STATES),
                f"{variant_id} reuses a complete state strip",
            )
            actor_signatures[variant_id] = actor_digest.hexdigest()

        self.assertEqual(len(set(actor_signatures.values())), len(MODEL_IDS))

    def test_authored_hands_hold_gear_and_release_points_remain_continuous(self) -> None:
        for variant_id in MODEL_IDS:
            kind = self._kind(variant_id)
            style = str(self.catalog[variant_id]["attack_style"])
            actor = animation_manifest.enemy_animation_actor(kind, variant_id)
            clip = animation_manifest.clip_for(actor, "attack")
            releases: list[tuple[int, tuple[int, int]]] = []
            for phase_index in range(clip.frame_count):
                tick = _pose_tick(clip, phase_index)
                metadata = sprite_atlas.enemy_pose_anchors(
                    kind,
                    "attack",
                    tick,
                    variant_id=variant_id,
                )
                hands = [
                    point
                    for point in (metadata.get("rear_hand"), metadata.get("lead_hand"))
                    if isinstance(point, tuple)
                ]
                self.assertEqual(len(hands), 2)
                weapon = metadata.get("weapon_anchor")
                if metadata.get("held_gear"):
                    self.assertIsInstance(weapon, tuple)
                    assert isinstance(weapon, tuple)
                    # The landmark may identify a long baton tip rather than
                    # its grip, but it must stay within one integrated prop
                    # length of an authored hand.
                    self.assertLessEqual(min(_point_distance(weapon, hand) for hand in hands), 32.0)

                release = sprite_atlas.enemy_release_anchor(
                    kind,
                    "attack",
                    tick,
                    variant_id=variant_id,
                )
                self.assertEqual(release, metadata.get("release_anchor"))
                if release is not None:
                    releases.append((phase_index, release))
                    self.assertLessEqual(min(_point_distance(release, hand) for hand in hands), 18.0)

            if style in PROJECTILE_STYLES:
                self.assertTrue(releases, f"{variant_id} has no authored release pose")
            else:
                self.assertEqual(releases, [], f"{variant_id} invents a projectile release")

    def test_approval_preview_is_exact_production_render_without_debug_overlay(self) -> None:
        base = self.preview._background(self.game)
        font = pygame.font.Font(None, 14)
        small_font = pygame.font.Font(None, 11)
        font.set_bold(True)
        small_font.set_bold(True)

        for variant_id in MODEL_IDS:
            with self.subTest(variant=variant_id):
                frames = self.preview._render_model(
                    self.game,
                    self.human,
                    base,
                    font,
                    small_font,
                    variant_id,
                    frame_count=1,
                )
                self.assertEqual(len(frames), 1)
                self.assertFalse(self.preview.has_debug_overlay_signature(frames[0]))

                kind = self._kind(variant_id)
                style = str(self.catalog[variant_id]["attack_style"])
                attack_x = 112.0 if style in self.preview.RANGED_STYLES else 220.0
                expected = base.copy()
                pixel_art.draw_enemy(
                    expected,
                    attack_x - 30.0,
                    151.0,
                    facing=1,
                    state="idle",
                    kind=f"{kind}:{variant_id}",
                    frame=0,
                )
                expected = pygame.transform.scale(expected, self.preview.OUTPUT_SIZE)
                self.assertEqual(
                    frames[0].tobytes(),
                    pygame.image.tobytes(expected, "RGB"),
                    "approval frame contains something besides production world and actor rendering",
                )

        debug_frame = self.preview._render_model(
            self.game,
            self.human,
            base,
            font,
            small_font,
            MODEL_IDS[0],
            debug_overlay=True,
            frame_count=1,
        )[0]
        self.assertTrue(self.preview.has_debug_overlay_signature(debug_frame))


if __name__ == "__main__":
    unittest.main()
