"""Deterministic, fail-closed environment authoring for the Fades world.

This module deliberately stops at authored composition.  It does not invent
art, change the renderer, or mutate a shipping level.  It selects approved
file-backed scenery and existing engine-authored interactive props, then
emits a manifest that can be reviewed or adapted to ``stage_chunks.json`` and
the current ``gameplay.json`` contracts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import random
import re
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
GENERATOR_VERSION = "environment-authoring-1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
LAYERS = ("sky", "far", "mid", "ground", "foreground")
WORLD_LAYERS = frozenset({"sky", "far", "mid", "ground", "foreground"})
INTERACTIVE_CATEGORIES = frozenset({"interactive", "hazard", "pickup", "throwable"})


class EnvironmentGenerationError(ValueError):
    """A recipe, module, asset, or generated manifest violates a contract."""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": sum(issue.severity == "warning" for issue in self.issues),
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class AssetRecord:
    path: str
    sha256: str
    size_bytes: int
    width: int | None
    height: int | None
    bit_depth: int | None
    color_type: int | None
    has_alpha: bool | None
    palette_colors: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArtStyleProfile:
    profile_id: str
    version: int
    logical_canvas: tuple[int, int]
    pixel_grid: int
    filtering: str
    anti_aliasing: str
    approved_assets: tuple[str, ...]
    denied_patterns: tuple[str, ...]
    approved_engine_sources: tuple[str, ...]
    camera_profile: str
    horizon_range: tuple[int, int]
    gameplay_lane: tuple[int, int]
    parallax_range: tuple[float, float]
    foreground_occlusion_budget: float
    foliage_density_range: tuple[float, float]
    prop_density_range: tuple[float, float]
    outline_policy: str
    ground_shadow_policy: str
    palette_families: Mapping[str, tuple[str, ...]]
    time_of_day_modifiers: Mapping[str, Mapping[str, float]]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, label: str = "style") -> "ArtStyleProfile":
        def pair(name: str, cast: Any) -> tuple[Any, Any]:
            raw = data.get(name)
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 2:
                raise EnvironmentGenerationError(f"{label}.{name} must contain two values")
            return cast(raw[0]), cast(raw[1])

        profile_id = str(data.get("profile_id", "")).strip()
        if not profile_id:
            raise EnvironmentGenerationError(f"{label}.profile_id is required")
        canvas = pair("logical_canvas", int)
        if canvas[0] <= 0 or canvas[1] <= 0:
            raise EnvironmentGenerationError(f"{label}.logical_canvas must be positive")
        approved = tuple(str(item).replace("\\", "/").strip() for item in data.get("approved_assets", ()))
        if not approved or any(not item.startswith("assets/") for item in approved):
            raise EnvironmentGenerationError(f"{label}.approved_assets must contain assets/... paths")
        denied = tuple(str(item).strip() for item in data.get("denied_patterns", ()))
        engine = tuple(str(item).replace("\\", "/").strip() for item in data.get("approved_engine_sources", ()))
        palette = {
            str(name): tuple(str(color) for color in colors)
            for name, colors in (data.get("palette_families") or {}).items()
        }
        modifiers = {
            str(name): {str(key): float(value) for key, value in values.items()}
            for name, values in (data.get("time_of_day_modifiers") or {}).items()
        }
        parallax = pair("parallax_range", float)
        if parallax[0] < 0 or parallax[1] < parallax[0]:
            raise EnvironmentGenerationError(f"{label}.parallax_range is invalid")
        return cls(
            profile_id=profile_id,
            version=int(data.get("version", 0)),
            logical_canvas=canvas,
            pixel_grid=int(data.get("pixel_grid", 1)),
            filtering=str(data.get("filtering", "")),
            anti_aliasing=str(data.get("anti_aliasing", "")),
            approved_assets=approved,
            denied_patterns=denied,
            approved_engine_sources=engine,
            camera_profile=str(data.get("camera_profile", "")),
            horizon_range=pair("horizon_range", int),
            gameplay_lane=pair("gameplay_lane", int),
            parallax_range=parallax,
            foreground_occlusion_budget=float(data.get("foreground_occlusion_budget", 0.0)),
            foliage_density_range=pair("foliage_density_range", float),
            prop_density_range=pair("prop_density_range", float),
            outline_policy=str(data.get("outline_policy", "")),
            ground_shadow_policy=str(data.get("ground_shadow_policy", "")),
            palette_families=palette,
            time_of_day_modifiers=modifiers,
        )


@dataclass(frozen=True, slots=True)
class EnvironmentModule:
    module_id: str
    category: str
    tags: tuple[str, ...]
    style_profiles: tuple[str, ...]
    source_type: str
    source: str
    native_dimensions: tuple[int, int]
    logical_width: int
    logical_depth: int
    layer: str
    parallax: float
    anchor: str
    left_socket: str | None
    right_socket: str | None
    allowed_adjacent_tags: tuple[str, ...]
    forbidden_adjacent_tags: tuple[str, ...]
    minimum_repeat_distance: int
    maximum_uses_per_visible_region: int
    collision: tuple[float, float, float, float] | None
    occlusion: tuple[float, float, float, float] | None
    navigation_exclusion: tuple[float, float, float, float] | None
    interaction: tuple[float, float, float, float] | None
    entrance_clearance: int
    exit_clearance: int
    spawn_clearance: int
    shadow: bool
    lighting_emitter: bool
    animated: bool
    time_of_day: tuple[str, ...]
    biome_tags: tuple[str, ...]
    rarity: str
    variants: tuple[str, ...]
    performance_cost: int
    supporting_modules: tuple[str, ...]
    source_attribution: str
    scale: int = 1
    mirror_group: str | None = None
    palette_variant_group: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, label: str = "module") -> "EnvironmentModule":
        def strings(name: str) -> tuple[str, ...]:
            raw = data.get(name, ())
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
                raise EnvironmentGenerationError(f"{label}.{name} must be a list")
            return tuple(str(item).strip() for item in raw if str(item).strip())

        def rect(name: str) -> tuple[float, float, float, float] | None:
            raw = data.get(name)
            if raw is None:
                return None
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 4:
                raise EnvironmentGenerationError(f"{label}.{name} must be [x, depth, width, height]")
            result = tuple(float(value) for value in raw)
            if result[2] <= 0 or result[3] <= 0:
                raise EnvironmentGenerationError(f"{label}.{name} must have positive size")
            return result  # type: ignore[return-value]

        module_id = str(data.get("module_id", "")).strip()
        source = str(data.get("source", "")).replace("\\", "/").strip()
        if not module_id or not source:
            raise EnvironmentGenerationError(f"{label} requires module_id and source")
        dimensions = data.get("native_dimensions", (0, 0))
        if not isinstance(dimensions, Sequence) or len(dimensions) != 2:
            raise EnvironmentGenerationError(f"{label}.native_dimensions must contain two values")
        return cls(
            module_id=module_id,
            category=str(data.get("category", "")).strip(),
            tags=strings("tags"),
            style_profiles=strings("style_profiles"),
            source_type=str(data.get("source_type", "file")).strip(),
            source=source,
            native_dimensions=(int(dimensions[0]), int(dimensions[1])),
            logical_width=int(data.get("logical_width", 0)),
            logical_depth=int(data.get("logical_depth", 0)),
            layer=str(data.get("layer", "")).strip(),
            parallax=float(data.get("parallax", 1.0)),
            anchor=str(data.get("anchor", "ground")).strip(),
            left_socket=(str(data["left_socket"]).strip() if data.get("left_socket") else None),
            right_socket=(str(data["right_socket"]).strip() if data.get("right_socket") else None),
            allowed_adjacent_tags=strings("allowed_adjacent_tags"),
            forbidden_adjacent_tags=strings("forbidden_adjacent_tags"),
            minimum_repeat_distance=int(data.get("minimum_repeat_distance", 0)),
            maximum_uses_per_visible_region=int(data.get("maximum_uses_per_visible_region", 1)),
            collision=rect("collision"),
            occlusion=rect("occlusion"),
            navigation_exclusion=rect("navigation_exclusion"),
            interaction=rect("interaction"),
            entrance_clearance=int(data.get("entrance_clearance", 0)),
            exit_clearance=int(data.get("exit_clearance", 0)),
            spawn_clearance=int(data.get("spawn_clearance", 0)),
            shadow=bool(data.get("shadow", False)),
            lighting_emitter=bool(data.get("lighting_emitter", False)),
            animated=bool(data.get("animated", False)),
            time_of_day=strings("time_of_day"),
            biome_tags=strings("biome_tags"),
            rarity=str(data.get("rarity", "common")),
            variants=strings("variants"),
            performance_cost=int(data.get("performance_cost", 1)),
            supporting_modules=strings("supporting_modules"),
            source_attribution=str(data.get("source_attribution", "")).strip(),
            scale=int(data.get("scale", 1)),
            mirror_group=(str(data["mirror_group"]).strip() if data.get("mirror_group") else None),
            palette_variant_group=(str(data["palette_variant_group"]).strip() if data.get("palette_variant_group") else None),
        )


@dataclass(frozen=True, slots=True)
class SceneZone:
    zone_id: str
    category: str
    width: int
    tags: tuple[str, ...]
    required_modules: tuple[str, ...]
    forbidden_modules: tuple[str, ...]
    landmark_slots: tuple[Mapping[str, Any], ...]
    prop_density: float
    foliage_density: float

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, label: str) -> "SceneZone":
        def strings(name: str) -> tuple[str, ...]:
            return tuple(str(item).strip() for item in data.get(name, ()) if str(item).strip())

        raw_slots = data.get("landmark_slots", ())
        if not isinstance(raw_slots, Sequence) or isinstance(raw_slots, (str, bytes)):
            raise EnvironmentGenerationError(f"{label}.landmark_slots must be a list")
        return cls(
            zone_id=str(data.get("zone_id", "")).strip(),
            category=str(data.get("category", "")).strip(),
            width=int(data.get("width", 0)),
            tags=strings("tags"),
            required_modules=strings("required_modules"),
            forbidden_modules=strings("forbidden_modules"),
            landmark_slots=tuple(item for item in raw_slots if isinstance(item, Mapping)),
            prop_density=float(data.get("prop_density", 0.0)),
            foliage_density=float(data.get("foliage_density", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class SceneRecipe:
    scene_id: str
    display_name: str
    version: int
    seed: int
    style_profile: str
    time_of_day: str
    location_theme: str
    target_length: int
    camera_profile: str
    zones: tuple[SceneZone, ...]
    landmark_slots: tuple[Mapping[str, Any], ...]
    ground_surface_profile: str
    foliage_profile: str
    prop_density: float
    interactive_item_budget: int
    encounter_clearance: int
    foreground_occlusion_budget: float
    weather_profile: str
    ambient_animation_budget: int
    required_modules: tuple[str, ...]
    forbidden_modules: tuple[str, ...]
    locked_modules: tuple[str, ...]
    unique_module_budget: int
    repeat_radius: int
    performance_budget: int
    export_mode: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, label: str = "recipe") -> "SceneRecipe":
        raw_zones = data.get("zone_sequence") or data.get("zones")
        if not isinstance(raw_zones, Sequence) or isinstance(raw_zones, (str, bytes)):
            raise EnvironmentGenerationError(f"{label}.zone_sequence must be a list")
        zones = tuple(
            SceneZone.from_mapping(zone, label=f"{label}.zone_sequence[{index}]")
            for index, zone in enumerate(raw_zones)
            if isinstance(zone, Mapping)
        )
        def strings(name: str) -> tuple[str, ...]:
            return tuple(str(item).strip() for item in data.get(name, ()) if str(item).strip())

        return cls(
            scene_id=str(data.get("scene_id", "")).strip(),
            display_name=str(data.get("display_name", "")).strip(),
            version=int(data.get("version", 1)),
            seed=int(data.get("seed", 0)),
            style_profile=str(data.get("style_profile", "")).strip(),
            time_of_day=str(data.get("time_of_day", "")).strip(),
            location_theme=str(data.get("location_theme", "")).strip(),
            target_length=int(data.get("target_length", 0)),
            camera_profile=str(data.get("camera_profile", "")).strip(),
            zones=zones,
            landmark_slots=tuple(item for item in data.get("landmark_slots", ()) if isinstance(item, Mapping)),
            ground_surface_profile=str(data.get("ground_surface_profile", "")).strip(),
            foliage_profile=str(data.get("foliage_profile", "")).strip(),
            prop_density=float(data.get("prop_density", 0.0)),
            interactive_item_budget=int(data.get("interactive_item_budget", 0)),
            encounter_clearance=int(data.get("encounter_clearance", 0)),
            foreground_occlusion_budget=float(data.get("foreground_occlusion_budget", 0.0)),
            weather_profile=str(data.get("weather_profile", "none")).strip(),
            ambient_animation_budget=int(data.get("ambient_animation_budget", 0)),
            required_modules=strings("required_modules"),
            forbidden_modules=strings("forbidden_modules"),
            locked_modules=strings("locked_modules"),
            unique_module_budget=int(data.get("unique_module_budget", 0)),
            repeat_radius=int(data.get("repeat_radius", 0)),
            performance_budget=int(data.get("performance_budget", 0)),
            export_mode=str(data.get("export_mode", "manifest")).strip(),
        )


@dataclass(frozen=True, slots=True)
class Placement:
    placement_id: str
    module_id: str
    zone_id: str
    x: int
    depth: int
    layer: str
    parallax: float
    scale: int
    variant: str | None = None
    locked: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, separators=(",", ": ")).encode("utf-8") + b"\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_path(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def _rect_intersects(first: Sequence[float], second: Sequence[float]) -> bool:
    ax, ad, aw, ah = first
    bx, bd, bw, bh = second
    return ax < bx + bw and ax + aw > bx and ad < bd + bh and ad + ah > bd


def _png_info(path: Path) -> tuple[int | None, int | None, int | None, int | None, bool | None, int | None]:
    try:
        raw = path.read_bytes()
    except OSError:
        return (None,) * 6
    if len(raw) < 33 or raw[:8] != PNG_SIGNATURE or raw[12:16] != b"IHDR":
        return (None,) * 6
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    bit_depth = raw[24]
    color_type = raw[25]
    has_alpha = color_type in (4, 6)
    palette_colors: int | None = None
    if color_type == 3:
        cursor = 8
        while cursor + 12 <= len(raw):
            length = int.from_bytes(raw[cursor:cursor + 4], "big")
            kind = raw[cursor + 4:cursor + 8]
            if kind == b"PLTE":
                palette_colors = length // 3
                break
            cursor += 12 + length
    return width, height, bit_depth, color_type, has_alpha, palette_colors


class EnvironmentLibrary:
    """Loads and validates the checked-in style/module library."""

    def __init__(self, project_root: Path, style_path: Path, module_path: Path) -> None:
        self.project_root = project_root.resolve()
        self.style_path = style_path
        self.module_path = module_path
        style_payload = json.loads(style_path.read_text(encoding="utf-8-sig"))
        profiles = style_payload.get("profiles") if isinstance(style_payload, Mapping) else None
        if not isinstance(profiles, Mapping):
            raise EnvironmentGenerationError("style library profiles must be an object")
        self.styles = {
            str(profile_id): ArtStyleProfile.from_mapping({**payload, "profile_id": profile_id}, label=f"profiles.{profile_id}")
            for profile_id, payload in profiles.items()
            if isinstance(payload, Mapping)
        }
        module_payload = json.loads(module_path.read_text(encoding="utf-8-sig"))
        raw_modules = module_payload.get("modules") if isinstance(module_payload, Mapping) else None
        if not isinstance(raw_modules, Sequence) or isinstance(raw_modules, (str, bytes)):
            raise EnvironmentGenerationError("module library modules must be a list")
        self.modules = {
            module.module_id: module
            for index, item in enumerate(raw_modules)
            if isinstance(item, Mapping)
            for module in (EnvironmentModule.from_mapping(item, label=f"modules[{index}]"),)
        }

    def style(self, profile_id: str) -> ArtStyleProfile:
        try:
            return self.styles[profile_id]
        except KeyError as error:
            raise EnvironmentGenerationError(f"style profile '{profile_id}' is not approved") from error

    def module(self, module_id: str) -> EnvironmentModule:
        try:
            return self.modules[module_id]
        except KeyError as error:
            raise EnvironmentGenerationError(f"module '{module_id}' is not approved") from error

    def asset_path(self, source: str) -> Path:
        relative = _normalise_path(source)
        if not relative.startswith("assets/") or ".." in Path(relative).parts:
            raise EnvironmentGenerationError(f"asset source '{source}' is outside assets/")
        candidate = (self.project_root / relative).resolve()
        assets_root = (self.project_root / "assets").resolve()
        if assets_root not in candidate.parents:
            raise EnvironmentGenerationError(f"asset source '{source}' escapes assets/")
        return candidate

    def validate_module(self, module: EnvironmentModule, style: ArtStyleProfile | None = None) -> ValidationReport:
        style = style or next(iter(self.styles.values()))
        issues: list[ValidationIssue] = []
        path = f"modules.{module.module_id}"
        if module.category not in {"sky", "architecture", "ground", "foliage", "prop", "interactive", "ambience", "foreground", "landmark"}:
            issues.append(ValidationIssue("error", "module.category", f"{path}.category", f"unsupported category '{module.category}'"))
        if module.layer not in WORLD_LAYERS:
            issues.append(ValidationIssue("error", "module.layer", f"{path}.layer", f"unsupported layer '{module.layer}'"))
        if module.logical_width <= 0 or module.logical_depth <= 0:
            issues.append(ValidationIssue("error", "module.dimensions", path, "logical_width and logical_depth must be positive"))
        if module.native_dimensions[0] <= 0 or module.native_dimensions[1] <= 0:
            issues.append(ValidationIssue("error", "module.native_dimensions", f"{path}.native_dimensions", "native dimensions must be positive"))
        if module.minimum_repeat_distance < 0 or module.maximum_uses_per_visible_region <= 0:
            issues.append(ValidationIssue("error", "module.repetition", f"{path}.minimum_repeat_distance", "repeat distance must be non-negative and usage cap positive"))
        if module.performance_cost <= 0:
            issues.append(ValidationIssue("error", "module.performance_cost", f"{path}.performance_cost", "performance cost must be positive"))
        if module.scale != 1:
            issues.append(ValidationIssue("error", "unsupported.scale", f"{path}.scale", "gameplay art must use integer native scale 1"))
        if module.parallax < style.parallax_range[0] or module.parallax > style.parallax_range[1]:
            issues.append(ValidationIssue("error", "module.parallax", f"{path}.parallax", "parallax is outside the style profile range"))
        if not module.source_attribution:
            issues.append(ValidationIssue("error", "source.attribution", f"{path}.source_attribution", "source attribution is required"))
        if module.source_type == "file":
            relative = _normalise_path(module.source)
            if relative not in style.approved_assets:
                issues.append(ValidationIssue("error", "asset.denied", f"{path}.source", "file is not on the approved allowlist"))
            if any(re.search(pattern, relative, flags=re.IGNORECASE) for pattern in style.denied_patterns):
                issues.append(ValidationIssue("error", "asset.denied", f"{path}.source", "file matches the denied-art pattern list"))
            candidate = self.asset_path(relative)
            if not candidate.is_file():
                issues.append(ValidationIssue("error", "asset.missing", f"{path}.source", f"missing approved asset {relative}"))
            else:
                width, height, *_ = _png_info(candidate)
                if (width, height) != module.native_dimensions:
                    issues.append(ValidationIssue("error", "asset.dimensions", f"{path}.native_dimensions", f"declared {module.native_dimensions} but asset is {(width, height)}"))
        elif module.source_type == "engine":
            if _normalise_path(module.source) not in style.approved_engine_sources:
                issues.append(ValidationIssue("error", "engine-source.denied", f"{path}.source", "engine source is not approved"))
        else:
            issues.append(ValidationIssue("error", "source.type", f"{path}.source_type", f"unsupported source type '{module.source_type}'"))
        if module.category in INTERACTIVE_CATEGORIES and module.collision is None:
            issues.append(ValidationIssue("error", "interactive.collision", f"{path}.collision", "interactive modules require a collision footprint"))
        if module.category in {"foliage", "prop", "interactive", "foreground"} and not module.shadow:
            issues.append(ValidationIssue("warning", "shadow.missing", f"{path}.shadow", "world props normally require a ground shadow"))
        return ValidationReport(tuple(issues))

    def validate_all(self, profile_id: str) -> ValidationReport:
        style = self.style(profile_id)
        issues: list[ValidationIssue] = []
        for module in self.modules.values():
            issues.extend(self.validate_module(module, style).issues)
        return ValidationReport(tuple(issues))

    def analyze_assets(self, profile_id: str) -> dict[str, Any]:
        style = self.style(profile_id)
        records: list[AssetRecord] = []
        missing: list[str] = []
        for relative in style.approved_assets:
            path = self.asset_path(relative)
            if not path.is_file():
                missing.append(relative)
                continue
            width, height, bit_depth, color_type, has_alpha, palette_colors = _png_info(path)
            records.append(AssetRecord(relative, _sha256(path), path.stat().st_size, width, height, bit_depth, color_type, has_alpha, palette_colors))
        widths = [record.width for record in records if record.width]
        heights = [record.height for record in records if record.height]
        return {
            "schema_version": SCHEMA_VERSION,
            "style_profile": profile_id,
            "approved_count": len(style.approved_assets),
            "analyzed_count": len(records),
            "missing_assets": missing,
            "assets": [record.as_dict() for record in records],
            "native_dimension_summary": {
                "widths": sorted(set(widths)),
                "heights": sorted(set(heights)),
                "likely_scale_inconsistency": len(set(widths)) > 3 or len(set(heights)) > 3,
            },
            "pixel_contract": {"filtering": style.filtering, "anti_aliasing": style.anti_aliasing, "grid": style.pixel_grid},
            "palette_analysis": "Pillow palette extraction is available through the CLI when installed; PNG palette metadata is recorded here.",
        }


class EnvironmentGenerator:
    """Create deterministic authored compositions from a recipe and seed."""

    def __init__(self, library: EnvironmentLibrary, recipe: SceneRecipe, *, seed: int | None = None) -> None:
        self.library = library
        self.recipe = recipe
        self.seed = recipe.seed if seed is None else int(seed)
        self.style = library.style(recipe.style_profile)
        self._module_issues = library.validate_all(recipe.style_profile)

    def validate_recipe(self) -> ValidationReport:
        issues = list(self._module_issues.issues)
        path = f"recipes.{self.recipe.scene_id}"
        if not self.recipe.scene_id:
            issues.append(ValidationIssue("error", "recipe.id", f"{path}.scene_id", "scene_id is required"))
        if self.recipe.seed < 0:
            issues.append(ValidationIssue("error", "recipe.seed", f"{path}.seed", "seed must be non-negative"))
        if self.recipe.target_length <= 0:
            issues.append(ValidationIssue("error", "recipe.length", f"{path}.target_length", "target_length must be positive"))
        if not self.recipe.zones:
            issues.append(ValidationIssue("error", "recipe.zones", f"{path}.zone_sequence", "at least one zone is required"))
        if sum(zone.width for zone in self.recipe.zones) != self.recipe.target_length:
            issues.append(ValidationIssue("error", "recipe.zone_widths", f"{path}.zone_sequence", "zone widths must equal target_length"))
        if self.recipe.camera_profile != self.style.camera_profile:
            issues.append(ValidationIssue("error", "recipe.camera_profile", f"{path}.camera_profile", "recipe camera profile is not the style profile camera"))
        if self.recipe.foreground_occlusion_budget > self.style.foreground_occlusion_budget:
            issues.append(ValidationIssue("error", "recipe.occlusion_budget", f"{path}.foreground_occlusion_budget", "recipe exceeds style occlusion budget"))
        if self.recipe.prop_density < self.style.prop_density_range[0] or self.recipe.prop_density > self.style.prop_density_range[1]:
            issues.append(ValidationIssue("error", "recipe.prop_density", f"{path}.prop_density", "prop density is outside the style range"))
        for zone in self.recipe.zones:
            zone_path = f"{path}.zone_sequence[{zone.zone_id}]"
            if zone.width <= 0:
                issues.append(ValidationIssue("error", "zone.width", f"{zone_path}.width", "zone width must be positive"))
            for module_id in (*zone.required_modules, *zone.forbidden_modules, *(str(slot.get("module_id")) for slot in zone.landmark_slots if slot.get("module_id"))):
                if module_id not in self.library.modules:
                    issues.append(ValidationIssue("error", "module.unknown", f"{zone_path}", f"module '{module_id}' is not in the approved library"))
        for module_id in (*self.recipe.required_modules, *self.recipe.forbidden_modules, *self.recipe.locked_modules):
            if module_id not in self.library.modules:
                issues.append(ValidationIssue("error", "module.unknown", path, f"module '{module_id}' is not in the approved library"))
        return ValidationReport(tuple(issues))

    def _eligible(self, category: str, zone: SceneZone) -> list[EnvironmentModule]:
        forbidden = set(self.recipe.forbidden_modules) | set(zone.forbidden_modules)
        modules = [
            module for module in self.library.modules.values()
            if module.category == category
            and module.module_id not in forbidden
            and self.recipe.style_profile in module.style_profiles
            and (not zone.tags or set(zone.tags).intersection(module.tags))
            and (not module.time_of_day or self.recipe.time_of_day in module.time_of_day)
        ]
        return sorted(modules, key=lambda module: module.module_id)

    def _choose(self, candidates: Sequence[EnvironmentModule], rng: random.Random, history: list[Placement], x: int, layer: str) -> EnvironmentModule:
        if not candidates:
            raise EnvironmentGenerationError(f"recipe '{self.recipe.scene_id}' has no approved module for layer={layer} at x={x}")
        filtered = [
            module for module in candidates
            if sum(placement.module_id == module.module_id for placement in history) < module.maximum_uses_per_visible_region
            and all(abs(placement.x - x) >= max(self.recipe.repeat_radius, module.minimum_repeat_distance) or placement.module_id != module.module_id for placement in history)
        ]
        if not filtered:
            filtered = list(candidates)
        weighted: list[EnvironmentModule] = []
        for module in filtered:
            weight = {"unique": 1, "uncommon": 2, "common": 4}.get(module.rarity, 1)
            weighted.extend([module] * weight)
        return rng.choice(weighted)

    def _place(self, placements: list[Placement], module: EnvironmentModule, zone: SceneZone, x: int, index: int, *, locked: bool = False) -> None:
        depth = self.style.gameplay_lane[0] if module.layer in {"ground", "foreground"} else self.style.horizon_range[1]
        placements.append(Placement(
            placement_id=f"{self.recipe.scene_id}:{zone.zone_id}:{module.module_id}:{index}",
            module_id=module.module_id,
            zone_id=zone.zone_id,
            x=int(x),
            depth=int(depth),
            layer=module.layer,
            parallax=module.parallax,
            scale=module.scale,
            variant=(module.variants[index % len(module.variants)] if module.variants else None),
            locked=locked,
        ))

    def _safe_x(self, placements: Sequence[Placement], module: EnvironmentModule, x: int) -> bool:
        if module.collision is None:
            return True
        cx, cd, cw, ch = module.collision
        candidate = (x + cx, cd, cw, ch)
        if candidate[0] < self.recipe.encounter_clearance or candidate[0] + candidate[2] > self.recipe.target_length - self.recipe.encounter_clearance:
            return False
        for placement in placements:
            other = self.library.module(placement.module_id)
            if other.collision is None:
                continue
            ox, od, ow, oh = other.collision
            if _rect_intersects(candidate, (placement.x + ox, od, ow, oh)):
                return False
        return True

    def generate(self, *, locked_placements: Mapping[str, Mapping[str, Any]] | None = None, zone_id: str | None = None) -> dict[str, Any]:
        report = self.validate_recipe()
        if not report.passed:
            first = report.errors[0]
            raise EnvironmentGenerationError(f"{first.path}: {first.message}")
        rng = random.Random(self.seed)
        placements: list[Placement] = []
        collision_records: list[dict[str, Any]] = []
        zone_records: list[dict[str, Any]] = []
        cursor = 0
        locked_placements = locked_placements or {}
        for zone in self.recipe.zones:
            if zone_id and zone.zone_id != zone_id:
                cursor += zone.width
                continue
            zone_start = cursor
            zone_end = cursor + zone.width
            zone_records.append({"zone_id": zone.zone_id, "category": zone.category, "world_x": zone_start, "width": zone.width})
            requested: list[tuple[str, int, str | None, bool]] = []
            requested.extend((module_id, zone_start + max(0, zone.width // 2), None, True) for module_id in zone.required_modules)
            requested.extend((str(slot.get("module_id")), zone_start + int(slot.get("x_offset", zone.width // 2)), str(slot.get("slot_id", "")) or None, True) for slot in zone.landmark_slots if slot.get("module_id"))
            required_categories = {
                self.library.module(module_id).category for module_id in zone.required_modules
            }
            required_categories.update(
                self.library.module(str(slot["module_id"])).category
                for slot in zone.landmark_slots
                if slot.get("module_id") in self.library.modules
            )
            for module_id, x, _slot, is_locked in requested:
                module = self.library.module(module_id)
                self._place(placements, module, zone, min(zone_end - 1, max(zone_start, x)), len(placements), locked=is_locked)
            for category, layer in (("sky", "sky"), ("architecture", "mid"), ("ground", "ground"), ("foreground", "foreground")):
                if category in required_categories:
                    continue
                candidates = self._eligible(category, zone)
                if not candidates:
                    continue
                module = self._choose(candidates, rng, placements, zone_start, layer)
                self._place(placements, module, zone, zone_start, len(placements))
            for category, density, layer in (("foliage", zone.foliage_density, "mid"), ("prop", zone.prop_density, "mid"), ("interactive", self.recipe.interactive_item_budget / max(1, len(self.recipe.zones)), "ground")):
                if category in required_categories:
                    continue
                candidates = self._eligible(category, zone)
                count = min(4 if category != "interactive" else 3, max(0, round(density * zone.width / 6.0)))
                if category == "interactive":
                    already_interactive = sum(self.library.module(item.module_id).category in INTERACTIVE_CATEGORIES for item in placements)
                    count = min(count, max(0, self.recipe.interactive_item_budget - already_interactive))
                for ordinal in range(count):
                    if not candidates:
                        break
                    x = zone_start + 48
                    module = self._choose(candidates, rng, placements, zone_start + zone.width // 2, layer)
                    for _attempt in range(32):
                        candidate_x = rng.randint(zone_start + 48, max(zone_start + 48, zone_end - 48))
                        if self._safe_x(placements, module, candidate_x) and all(
                            placement.module_id != module.module_id
                            or abs(placement.x - candidate_x) >= max(self.recipe.repeat_radius, module.minimum_repeat_distance)
                            for placement in placements
                        ):
                            x = candidate_x
                            break
                    if not self._safe_x(placements, module, x) or any(
                        placement.module_id == module.module_id
                        and abs(placement.x - x) < max(self.recipe.repeat_radius, module.minimum_repeat_distance)
                        for placement in placements
                    ):
                        continue
                    self._place(placements, module, zone, x, len(placements))
            cursor = zone_end
        for lock_id, lock in locked_placements.items():
            if not isinstance(lock, Mapping) or lock.get("module_id") not in self.library.modules:
                raise EnvironmentGenerationError(f"locks.{lock_id}.module_id: module is not approved")
            if lock_id not in {placement.placement_id for placement in placements}:
                module = self.library.module(str(lock["module_id"]))
                zone = next((zone for zone in self.recipe.zones if zone.zone_id == str(lock.get("zone_id"))), self.recipe.zones[0])
                self._place(placements, module, zone, int(lock.get("x", 0)), len(placements), locked=True)
        placements.sort(key=lambda placement: (placement.x, placement.layer, placement.placement_id))
        for placement in placements:
            module = self.library.module(placement.module_id)
            if module.collision:
                x, depth, width, height = module.collision
                collision_records.append({"id": placement.placement_id, "module_id": module.module_id, "x": placement.x + x, "depth": placement.depth + depth, "width": width, "height": height})
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "recipe": {
                "scene_id": self.recipe.scene_id,
                "version": self.recipe.version,
                "style_profile": self.recipe.style_profile,
                "seed": self.seed,
                "location_theme": self.recipe.location_theme,
                "target_length": self.recipe.target_length,
            },
            "zones": zone_records,
            "placements": [placement.as_dict() for placement in placements],
            "collision": collision_records,
            "entrances": [{"id": "entrance_left", "x": 32, "clearance": self.recipe.encounter_clearance}, {"id": "exit_right", "x": self.recipe.target_length - 32, "clearance": self.recipe.encounter_clearance}],
            "encounter_clearance": [{"zone_id": zone.zone_id, "x_min": next(record["world_x"] for record in zone_records if record["zone_id"] == zone.zone_id) + self.recipe.encounter_clearance, "x_max": next(record["world_x"] + record["width"] for record in zone_records if record["zone_id"] == zone.zone_id) - self.recipe.encounter_clearance} for zone in self.recipe.zones if any(record["zone_id"] == zone.zone_id for record in zone_records)],
            "spawn_markers": [{"id": "spawn_left", "x": 96, "depth": self.style.gameplay_lane[0]}, {"id": "spawn_right", "x": self.recipe.target_length - 96, "depth": self.style.gameplay_lane[0]}],
            "layer_contract": {layer: {"parallax": self.style.parallax_range[1] if layer == "foreground" else self.style.parallax_range[0] if layer in {"sky", "far"} else 1.0, "sort_anchor": "ground_contact"} for layer in LAYERS},
            "environment_animation": {"budget": self.recipe.ambient_animation_budget, "weather_profile": self.recipe.weather_profile, "time_of_day": self.recipe.time_of_day},
            "repetition_report": self._repetition_report(placements),
            "source_attribution": self._source_attribution(placements),
            "coverage": {"approved_modules_used": sorted({placement.module_id for placement in placements}), "missing_module_families": self._missing_families(placements)},
            "native_stage_world": self._native_stage_world(placements, zone_records),
        }
        payload["manifest_sha256"] = hashlib.sha256(_canonical_json(payload)).hexdigest()
        return payload

    def _native_stage_world(self, placements: Sequence[Placement], zones: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Emit a reviewable StageWorld-shaped adapter without changing runtime data."""

        layer_names = {"far": "far_skyline", "mid": "architecture", "ground": "ground", "foreground": "near_occluder"}
        chunks: list[dict[str, Any]] = []
        haze = next((path for path in self.style.approved_assets if "/atmosphere_haze_tile_v1.png" in path), None)
        if haze is None:
            raise EnvironmentGenerationError("style profile has no approved atmosphere haze tile for native_stage_world")
        for zone in zones:
            zone_id = str(zone["zone_id"])
            zone_placements = [placement for placement in placements if placement.zone_id == zone_id]
            layers: dict[str, dict[str, Any]] = {}
            for source_layer, native_layer in layer_names.items():
                candidate = next((placement for placement in zone_placements if placement.layer == source_layer and self.library.module(placement.module_id).source_type == "file"), None)
                if candidate is None:
                    raise EnvironmentGenerationError(f"zone {zone_id} has no file-backed {source_layer} layer for native_stage_world")
                module = self.library.module(candidate.module_id)
                layers[native_layer] = {
                    "asset": module.source,
                    "world_x": int(zone["world_x"]),
                    "width": module.native_dimensions[0],
                    "height": module.native_dimensions[1],
                    "source_layer": source_layer,
                }
            chunks.append({
                "id": f"{self.recipe.scene_id}_{zone_id}",
                "world_x": int(zone["world_x"]),
                "width": int(zone["width"]),
                "landmark_ids": [],
                "collision_ids": [placement.placement_id for placement in zone_placements if self.library.module(placement.module_id).collision],
                "physical_scene_object_ids": [],
                "spawn_markers": [],
                "foreground_layers": ["near_occluder"],
                "seam_anchor": "structural_handoff" if int(zone["world_x"]) + int(zone["width"]) < self.recipe.target_length else "",
                "layers": layers,
            })
        return {
            "schema_version": 1,
            "description": "Generated authoring output; review and migrate through the existing StageWorld contract before shipping.",
            "routes": [{
                "theme": self.recipe.location_theme,
                "world_width": self.recipe.target_length,
                "chunk_overlap": 0,
                "global_layers": {"far_haze": haze},
                "chunks": chunks,
            }],
        }

    def _repetition_report(self, placements: Sequence[Placement]) -> dict[str, Any]:
        violations: list[dict[str, Any]] = []
        for first_index, first in enumerate(placements):
            for second in placements[first_index + 1:]:
                if first.module_id != second.module_id:
                    continue
                module = self.library.module(first.module_id)
                if abs(first.x - second.x) < max(self.recipe.repeat_radius, module.minimum_repeat_distance):
                    violations.append({"first": first.placement_id, "second": second.placement_id, "distance": abs(first.x - second.x), "required": max(self.recipe.repeat_radius, module.minimum_repeat_distance)})
        return {"passed": not violations, "violations": violations, "unique_module_count": len({placement.module_id for placement in placements})}

    def _source_attribution(self, placements: Sequence[Placement]) -> list[dict[str, Any]]:
        records = []
        for module_id in sorted({placement.module_id for placement in placements}):
            module = self.library.module(module_id)
            record: dict[str, Any] = {"module_id": module_id, "source_type": module.source_type, "source": module.source, "attribution": module.source_attribution}
            if module.source_type == "file":
                path = self.library.asset_path(module.source)
                record["sha256"] = _sha256(path) if path.is_file() else None
            records.append(record)
        return records

    def _missing_families(self, placements: Sequence[Placement]) -> list[str]:
        present = {self.library.module(placement.module_id).category for placement in placements}
        return sorted({"trees", "bushes", "vehicles", "signs", "lights"} - present)

    def validate_manifest(self, manifest: Mapping[str, Any]) -> ValidationReport:
        issues: list[ValidationIssue] = []
        placements = manifest.get("placements")
        if not isinstance(placements, Sequence) or isinstance(placements, (str, bytes)):
            return ValidationReport((ValidationIssue("error", "manifest.placements", "manifest.placements", "placements must be a list"),))
        width = int(self.recipe.target_length)
        boxes: list[tuple[str, tuple[float, float, float, float]]] = []
        foreground_area = 0.0
        for index, record in enumerate(placements):
            path = f"manifest.placements[{index}]"
            if not isinstance(record, Mapping):
                issues.append(ValidationIssue("error", "placement.type", path, "placement must be an object"))
                continue
            module_id = str(record.get("module_id", ""))
            try:
                module = self.library.module(module_id)
            except EnvironmentGenerationError as error:
                issues.append(ValidationIssue("error", "module.unknown", f"{path}.module_id", str(error)))
                continue
            x = int(record.get("x", -1))
            if x < 0 or x >= width:
                issues.append(ValidationIssue("error", "placement.bounds", f"{path}.x", f"x={x} is outside [0,{width})"))
            if int(record.get("scale", 0)) != 1:
                issues.append(ValidationIssue("error", "placement.scale", f"{path}.scale", "placement scale must be 1"))
            if int(record.get("x", 0)) != float(record.get("x", 0)):
                issues.append(ValidationIssue("error", "placement.pixel_grid", f"{path}.x", "placement must be integer aligned"))
            if module.collision:
                cx, cd, cw, ch = module.collision
                placement_depth = float(record.get("depth", self.style.gameplay_lane[0]))
                box = (x + cx, placement_depth + cd, cw, ch)
                for other_id, other_box in boxes:
                    if _rect_intersects(box, other_box):
                        issues.append(ValidationIssue("error", "collision.overlap", path, f"collision overlaps {other_id}"))
                boxes.append((str(record.get("placement_id", path)), box))
            if module.layer == "foreground" and module.occlusion:
                foreground_area += module.occlusion[2] * module.occlusion[3]
            if module.parallax < self.style.parallax_range[0] or module.parallax > self.style.parallax_range[1]:
                issues.append(ValidationIssue("error", "parallax.range", f"{path}.parallax", "placement parallax is outside the style range"))
            if module.layer not in WORLD_LAYERS:
                issues.append(ValidationIssue("error", "layer.invalid", f"{path}.layer", "placement layer is not recognized"))
        if foreground_area > self.recipe.target_length * self.style.logical_canvas[1] * self.recipe.foreground_occlusion_budget:
            issues.append(ValidationIssue("error", "foreground.occlusion", "manifest.placements", "foreground occlusion exceeds the recipe budget"))
        unique_count = len({str(record.get("module_id", "")) for record in placements if isinstance(record, Mapping)})
        if unique_count > self.recipe.unique_module_budget:
            issues.append(ValidationIssue("error", "module.unique_budget", "manifest.placements", f"manifest uses {unique_count} unique modules; budget is {self.recipe.unique_module_budget}"))
        repetition = manifest.get("repetition_report")
        if not isinstance(repetition, Mapping) or not bool(repetition.get("passed", False)):
            issues.append(ValidationIssue("error", "repetition", "manifest.repetition_report", "repetition report did not pass"))
        source_attribution = manifest.get("source_attribution")
        if not isinstance(source_attribution, Sequence) or not source_attribution:
            issues.append(ValidationIssue("error", "source.attribution", "manifest.source_attribution", "manifest source attribution is required"))
        else:
            attributed = {str(item.get("module_id")) for item in source_attribution if isinstance(item, Mapping)}
            used = {str(record.get("module_id")) for record in placements if isinstance(record, Mapping)}
            for module_id in sorted(used - attributed):
                issues.append(ValidationIssue("error", "source.attribution", "manifest.source_attribution", f"missing attribution for {module_id}"))
        collision_boxes = []
        for record in placements:
            if not isinstance(record, Mapping):
                continue
            module = self.library.modules.get(str(record.get("module_id")))
            if module is None or module.collision is None:
                continue
            x, depth, width_box, height_box = module.collision
            collision_boxes.append((str(record.get("placement_id", "placement")), (float(record.get("x", 0)) + x, float(record.get("depth", self.style.gameplay_lane[0])) + depth, width_box, height_box)))
        for spawn in manifest.get("spawn_markers", ()):
            if not isinstance(spawn, Mapping):
                continue
            point_x = float(spawn.get("x", 0))
            point_depth = float(spawn.get("depth", self.style.gameplay_lane[0]))
            if any(box[0] <= point_x <= box[0] + box[2] and box[1] <= point_depth <= box[1] + box[3] for _id, box in collision_boxes):
                issues.append(ValidationIssue("error", "spawn.collision", "manifest.spawn_markers", f"spawn at ({point_x:g},{point_depth:g}) is inside a collision footprint"))
        clearance = self.recipe.encounter_clearance
        for placement_id, box in collision_boxes:
            if box[0] < clearance or box[0] + box[2] > width - clearance:
                issues.append(ValidationIssue("error", "entrance.clearance", "manifest.placements", f"{placement_id} blocks an entrance or exit clearance"))
        total_cost = sum(self.library.module(str(record.get("module_id"))).performance_cost for record in placements if isinstance(record, Mapping) and str(record.get("module_id")) in self.library.modules)
        if total_cost > self.recipe.performance_budget:
            issues.append(ValidationIssue("error", "performance.budget", "manifest.placements", f"performance cost {total_cost} exceeds budget {self.recipe.performance_budget}"))
        interactive_count = sum(self.library.module(str(record.get("module_id"))).category in INTERACTIVE_CATEGORIES for record in placements if isinstance(record, Mapping) and str(record.get("module_id")) in self.library.modules)
        if interactive_count > self.recipe.interactive_item_budget:
            issues.append(ValidationIssue("error", "interactive.budget", "manifest.placements", f"interactive count {interactive_count} exceeds budget {self.recipe.interactive_item_budget}"))
        lane_samples = max(1, width // 16)
        blocked_samples = sum(any(box[0] <= sample * 16 <= box[0] + box[2] for _id, box in collision_boxes) for sample in range(lane_samples))
        if blocked_samples / lane_samples > 0.30:
            issues.append(ValidationIssue("error", "combat.lane", "manifest.collision", "collision footprints block more than 30% of the main combat lane"))
        return ValidationReport(tuple(issues))


def load_recipe(path: Path) -> SceneRecipe:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, Mapping):
        raise EnvironmentGenerationError(f"recipe {path} must be an object")
    return SceneRecipe.from_mapping(payload, label=str(path))


def load_library(project_root: Path, *, style_path: Path | None = None, module_path: Path | None = None) -> EnvironmentLibrary:
    root = project_root.resolve()
    return EnvironmentLibrary(
        root,
        style_path or root / "data/content-generation/style_profiles.json",
        module_path or root / "data/content-generation/modules.json",
    )


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(payload))


__all__ = [
    "ArtStyleProfile",
    "EnvironmentGenerationError",
    "EnvironmentGenerator",
    "EnvironmentLibrary",
    "EnvironmentModule",
    "Placement",
    "SceneRecipe",
    "SceneZone",
    "ValidationIssue",
    "ValidationReport",
    "load_library",
    "load_recipe",
    "write_json",
]
