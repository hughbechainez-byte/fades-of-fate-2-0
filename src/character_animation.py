"""Character-specific art skins layered over reusable animation motion clips.

Motion data deliberately stops at joints, timing, contacts, and root travel.
The remaining contracts keep each character's authored proportions, complete
cels, layer policy, and native-pixel cleanup independent from that motion.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class GenericMotionClip:
    name: str
    pose_data_path: str
    fingerprint_sha256: str
    pose_count: int
    loop_duration_ms: int
    frozen_fields: tuple[str, ...]


@dataclass(frozen=True)
class CharacterProportionProfile:
    name: str
    native_cell_size: tuple[int, int]
    ruler_source: Mapping[str, Any]
    measurements_px: Mapping[str, Any]
    limb_length_ratios: Mapping[str, float]
    root_x_px: int
    ground_y_px: int


@dataclass(frozen=True)
class CharacterArtModel:
    name: str
    source_commit: str
    asset_inventory: tuple[Mapping[str, Any], ...]
    approved_reference_frames: tuple[Mapping[str, Any], ...]
    walk_source: Mapping[str, Any]
    master_palette: tuple[tuple[int, int, int, int], ...]
    palette_ramps: Mapping[str, tuple[str, ...]]
    light_direction: str


@dataclass(frozen=True)
class CharacterLayerRules:
    mode: str
    phase_source_indices: tuple[int, ...]
    near_side: str
    layer_order: tuple[str, ...]
    hidden_surface_policy: str


@dataclass(frozen=True)
class CharacterCleanupRules:
    alpha_threshold: int
    resampling: str
    hard_alpha: bool
    integer_coordinates: bool
    palette_lock: bool
    root_x_px: int
    ground_y_px: int
    forbidden_methods: tuple[str, ...]


@dataclass(frozen=True)
class CharacterAnimationSkin:
    schema_version: int
    character: str
    motion: GenericMotionClip
    proportions: CharacterProportionProfile
    art: CharacterArtModel
    layers: CharacterLayerRules
    cleanup: CharacterCleanupRules
    identity_validation: Mapping[str, Any]


# Animation V2 uses these value objects as the one boundary shared by the
# compiler, atlas loader, combat runtime and renderer.  They intentionally
# carry complete authored cels and explicit roots instead of pixel-fitting a
# body or inferring a ground line at draw time.
@dataclass(frozen=True, slots=True)
class PoseAnchor:
    """A named integer-space landmark inside one complete authored cel."""

    name: str
    position: tuple[int, int]


@dataclass(frozen=True, slots=True)
class VfxSocket:
    """Author-owned VFX placement metadata for one pose."""

    name: str
    position: tuple[int, int]
    tangent: tuple[int, int]
    size: int
    intensity: int
    visibility: str
    contact_anchor: str | None = None
    release_anchor: str | None = None


@dataclass(frozen=True, slots=True)
class AnimationEvent:
    """A non-damaging authored event emitted by an animation phase."""

    name: str
    phase: int
    payload: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class VfxPlacement:
    """A resolved rear/body/front placement supplied with an animation sample."""

    asset_id: str
    socket: VfxSocket
    layer: str
    event_name: str | None = None


@dataclass(frozen=True, slots=True)
class AnimationSample:
    """Immutable root-aware presentation result for one playable actor pose.

    ``body_surface`` is an already authored, cached pygame surface.  Consumers
    may blit it but must not mutate it; the frozen structure prevents combat and
    VFX systems from changing the chosen clip, root, anchors or body bounds.
    """

    actor_id: str
    clip_id: str
    pose_index: int
    body_surface: object
    root: tuple[int, int]
    body_bounds: tuple[int, int, int, int]
    anchors: tuple[PoseAnchor, ...]
    events: tuple[AnimationEvent, ...]
    rear_vfx: tuple[VfxPlacement, ...]
    front_vfx: tuple[VfxPlacement, ...]


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return MappingProxyType(value)


def _positive_pair(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must contain two integers")
    pair = int(value[0]), int(value[1])
    if min(pair) <= 0:
        raise ValueError(f"{label} must be positive")
    return pair


def _palette(value: object) -> tuple[tuple[int, int, int, int], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("art_model.master_palette_hex must be a non-empty list")
    result: list[tuple[int, int, int, int]] = []
    for raw in value:
        if not isinstance(raw, str) or len(raw) != 7 or not raw.startswith("#"):
            raise ValueError(f"invalid palette color: {raw!r}")
        try:
            red, green, blue = (int(raw[index : index + 2], 16) for index in (1, 3, 5))
        except ValueError as error:
            raise ValueError(f"invalid palette color: {raw!r}") from error
        result.append((red, green, blue, 255))
    if len(set(result)) != len(result):
        raise ValueError("art model palette contains duplicate colors")
    return tuple(result)


def load_character_animation_skin(path: Path) -> CharacterAnimationSkin:
    """Load and strictly validate one reusable-motion/character-art contract."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported character animation skin schema")

    motion = _mapping(payload.get("generic_motion_clip"), "generic_motion_clip")
    proportions = _mapping(payload.get("proportion_profile"), "proportion_profile")
    art = _mapping(payload.get("art_model"), "art_model")
    layers = _mapping(payload.get("layer_rules"), "layer_rules")
    cleanup = _mapping(payload.get("cleanup_rules"), "cleanup_rules")
    validation = _mapping(payload.get("identity_validation"), "identity_validation")

    palette_ramps = _mapping(art.get("palette_ramps"), "art_model.palette_ramps")
    frozen_ramps = MappingProxyType(
        {
            str(name): tuple(str(color) for color in colors)
            for name, colors in palette_ramps.items()
            if isinstance(colors, list)
        }
    )
    if len(frozen_ramps) != len(palette_ramps):
        raise ValueError("every palette ramp must be a list")

    return CharacterAnimationSkin(
        schema_version=1,
        character=str(payload.get("character", "")),
        motion=GenericMotionClip(
            name=str(motion.get("name", "")),
            pose_data_path=str(motion.get("pose_data_path", "")),
            fingerprint_sha256=str(motion.get("fingerprint_sha256", "")),
            pose_count=int(motion.get("pose_count", 0)),
            loop_duration_ms=int(motion.get("loop_duration_ms", 0)),
            frozen_fields=tuple(str(item) for item in motion.get("frozen_fields", [])),
        ),
        proportions=CharacterProportionProfile(
            name=str(proportions.get("name", "")),
            native_cell_size=_positive_pair(
                proportions.get("native_cell_size"),
                "proportion_profile.native_cell_size",
            ),
            ruler_source=_mapping(proportions.get("ruler_source"), "proportion_profile.ruler_source"),
            measurements_px=_mapping(
                proportions.get("measurements_px"),
                "proportion_profile.measurements_px",
            ),
            limb_length_ratios=MappingProxyType(
                {
                    str(name): float(value)
                    for name, value in _mapping(
                        proportions.get("limb_length_ratios"),
                        "proportion_profile.limb_length_ratios",
                    ).items()
                }
            ),
            root_x_px=int(proportions.get("root_x_px", -1)),
            ground_y_px=int(proportions.get("ground_y_px", -1)),
        ),
        art=CharacterArtModel(
            name=str(art.get("name", "")),
            source_commit=str(art.get("source_commit", "")),
            asset_inventory=tuple(
                _mapping(item, "art_model.asset_inventory entry")
                for item in art.get("asset_inventory", [])
            ),
            approved_reference_frames=tuple(
                _mapping(item, "art_model.approved_reference_frames entry")
                for item in art.get("approved_reference_frames", [])
            ),
            walk_source=_mapping(art.get("walk_source"), "art_model.walk_source"),
            master_palette=_palette(art.get("master_palette_hex")),
            palette_ramps=frozen_ramps,
            light_direction=str(art.get("light_direction", "")),
        ),
        layers=CharacterLayerRules(
            mode=str(layers.get("mode", "")),
            phase_source_indices=tuple(int(item) for item in layers.get("phase_source_indices", [])),
            near_side=str(layers.get("near_side", "")),
            layer_order=tuple(str(item) for item in layers.get("layer_order", [])),
            hidden_surface_policy=str(layers.get("hidden_surface_policy", "")),
        ),
        cleanup=CharacterCleanupRules(
            alpha_threshold=int(cleanup.get("alpha_threshold", -1)),
            resampling=str(cleanup.get("resampling", "")),
            hard_alpha=bool(cleanup.get("hard_alpha")),
            integer_coordinates=bool(cleanup.get("integer_coordinates")),
            palette_lock=bool(cleanup.get("palette_lock")),
            root_x_px=int(cleanup.get("root_x_px", -1)),
            ground_y_px=int(cleanup.get("ground_y_px", -1)),
            forbidden_methods=tuple(str(item) for item in cleanup.get("forbidden_methods", [])),
        ),
        identity_validation=validation,
    )
