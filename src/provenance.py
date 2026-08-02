"""Runtime and artifact provenance for the canonical cross-platform build."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
SCENE_DEFINITION = "data/chapter1_location_lock.json"
SCENERY_FIELDS = (
    "main_panorama_asset",
    "far_asset",
    "near_asset",
    "far_haze_asset",
    "far_skyline_asset",
    "architecture_asset",
    "ground_asset",
    "near_occluder_asset",
)
RENDERED_WITH_AUTHORED_MAIN = {
    "main_panorama_asset",
    "far_haze_asset",
    "far_skyline_asset",
    "ground_asset",
    "near_occluder_asset",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131_072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _git_dirty(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(result.stdout.strip())


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _runtime_platform() -> str:
    if (
        os.environ.get("ANDROID_ARGUMENT")
        or os.environ.get("ANDROID_PRIVATE")
        or os.environ.get("ANDROID_ROOT")
        or sys.platform.startswith("android")
    ):
        return "android"
    return "pc"


def _artifact_provenance(root: Path) -> tuple[Mapping[str, Any], Path | None]:
    candidates = [root / "build_provenance.json"]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "build_provenance.json")
    bundled = Path(getattr(sys, "_MEIPASS", root)).resolve()
    candidates.append(bundled / "build_provenance.json")
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return _read_json(resolved), resolved
    return {}, None


def _asset_records(root: Path, route: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    authored_main = bool(str(route.get("main_panorama_asset", "")).strip())
    canonical_root = (root / "assets").resolve()
    for field in SCENERY_FIELDS:
        relative = str(route.get(field, "")).strip()
        if not relative:
            continue
        path = (root / relative).resolve()
        canonical = path == canonical_root or canonical_root in path.parents
        rendered = not authored_main or field in RENDERED_WITH_AUTHORED_MAIN
        record: dict[str, Any] = {
            "field": field,
            "path": relative.replace("\\", "/"),
            "resolved_path": str(path),
            "canonical": canonical,
            "rendered": rendered,
        }
        if path.is_file():
            record.update(
                {
                    "sha256": sha256_path(path),
                    "size": path.stat().st_size,
                    "resolved": True,
                }
            )
        else:
            record.update({"sha256": "", "size": 0, "resolved": False})
        records.append(record)
    return records


def build_runtime_provenance(
    root: str | Path,
    *,
    game_version: str,
    platform: str | None,
    level_id: str,
    route: Mapping[str, Any],
    renderer: str,
    fallback_asset_used: bool = False,
    cached_asset_used: bool = False,
) -> dict[str, Any]:
    project_root = Path(root).resolve()
    manifest_path = project_root / "data" / "content-manifest.json"
    scene_path = project_root / SCENE_DEFINITION
    manifest = _read_json(manifest_path)
    artifact, artifact_path = _artifact_provenance(project_root)
    assets = _asset_records(project_root, route)

    atmosphere = _read_json(project_root / "data" / "atmosphere.json")
    profiles = atmosphere.get("profiles", {})
    route_map = atmosphere.get("route_profile_map", {})
    profile_id = route_map.get(level_id, "") if isinstance(route_map, Mapping) else ""
    profile = profiles.get(profile_id, {}) if isinstance(profiles, Mapping) else {}
    cloud_speeds = profile.get("cloud_speeds", ()) if isinstance(profile, Mapping) else ()
    ambient_count = 1 + len(cloud_speeds) if isinstance(cloud_speeds, (list, tuple)) else 1

    location_manifest = _read_json(scene_path)
    vehicle_variants = {
        (
            str(feature.get("asset", "")),
            tuple(feature.get("paint_color", ())),
            str(feature.get("condition", "")),
            str(feature.get("accessory", "")),
            int(feature.get("facing", 1)),
        )
        for location_route in location_manifest.get("routes", ())
        if isinstance(location_route, Mapping)
        for feature in location_route.get("physical_scene_objects", ())
        if isinstance(feature, Mapping)
    }
    source_head = _git_head(project_root)
    artifact_head = str(
        artifact.get("game_git_commit", artifact.get("source_commit", ""))
    ).strip()
    manifest_hash = sha256_path(manifest_path) if manifest_path.is_file() else ""
    expected_manifest_hash = str(artifact.get("content_manifest_sha256", "")).strip()
    artifact_match: bool | str = "source"
    if artifact_path is not None:
        artifact_match = bool(expected_manifest_hash and manifest_hash == expected_manifest_hash)
        expected_platform = str(artifact.get("platform", "")).strip().lower()
        actual_platform = (platform or _runtime_platform()).lower()
        if expected_platform and expected_platform not in {actual_platform, "both"}:
            artifact_match = False
        expected_executable = str(artifact.get("pc_executable_sha256", "")).strip().lower()
        if expected_executable and getattr(sys, "frozen", False):
            try:
                artifact_match = bool(
                    artifact_match
                    and sha256_path(Path(sys.executable).resolve()).lower() == expected_executable
                )
            except OSError:
                artifact_match = False

    rendered_assets = [record for record in assets if record["rendered"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "game_git_commit": artifact_head or source_head,
        "working_tree_dirty": _git_dirty(project_root) if source_head != "unknown" else False,
        "game_version": str(game_version),
        "content_git_commit": str(manifest.get("source_commit", source_head)),
        "content_revision": manifest.get("content_revision", "unknown"),
        "content_manifest_hash": manifest_hash,
        "content_manifest_path": str(manifest_path),
        "build_timestamp": str(artifact.get("build_timestamp", "source")),
        "platform": platform or _runtime_platform(),
        "active_level_id": str(level_id),
        "scene_definition_path": SCENE_DEFINITION,
        "scene_definition_resolved_path": str(scene_path),
        "scene_definition_sha256": sha256_path(scene_path) if scene_path.is_file() else "",
        "active_background_renderer": str(renderer),
        "canonical_asset_root": str(project_root / "assets"),
        "active_scenery_assets": assets,
        "background_layers": len(rendered_assets),
        "animated_environment_entities": ambient_count,
        "vehicle_variants": len(vehicle_variants),
        "fallback_asset_used": bool(fallback_asset_used),
        "cached_asset_used": bool(cached_asset_used),
        "artifact_match": artifact_match,
        "build_provenance_path": str(artifact_path) if artifact_path is not None else "source",
        "all_assets_resolved": all(record["resolved"] for record in rendered_assets),
        "noncanonical_asset_used": any(not record["canonical"] for record in rendered_assets),
    }


def build_artifact_provenance(
    root: str | Path,
    *,
    platform: str,
    game_version: str,
    content_revision: int,
    content_manifest_sha256: str,
    content_pack_sha256: str,
    content_pack_size: int,
    build_timestamp: str | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    project_root = Path(root).resolve()
    commit = str(source_commit or _git_head(project_root))
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "build_timestamp": build_timestamp or datetime.now(timezone.utc).isoformat(),
        "platform": str(platform),
        "game_version": str(game_version),
        "game_git_commit": commit,
        "working_tree_dirty": _git_dirty(project_root),
        "content_git_commit": commit,
        "content_revision": int(content_revision),
        "content_manifest_sha256": str(content_manifest_sha256),
        "content_pack_sha256": str(content_pack_sha256),
        "content_pack_size": int(content_pack_size),
        "canonical_source_root": str(project_root),
        "canonical_asset_root": str(project_root / "assets"),
        "fallback_asset_used": False,
        "cached_asset_used": False,
    }
    identity = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["artifact_id"] = hashlib.sha256(identity).hexdigest()
    return payload


def write_provenance(path: str | Path, payload: Mapping[str, Any]) -> Path:
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(dict(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output


__all__ = [
    "SCENE_DEFINITION",
    "SCENERY_FIELDS",
    "build_artifact_provenance",
    "build_runtime_provenance",
    "sha256_path",
    "write_provenance",
]
