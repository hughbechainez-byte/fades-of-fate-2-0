"""Build one deterministic content package for both PC and Android."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.provenance import (  # noqa: E402
    build_artifact_provenance,
    sha256_path,
    write_provenance,
)
from src.version import VERSION  # noqa: E402


MANIFEST_ASSET = "fades-of-fate-content-manifest.json"
PC_MANIFEST_ASSET = "fades-of-fate-content-manifest-pc.json"
ANDROID_MANIFEST_ASSET = "fades-of-fate-content-manifest-android.json"
PACK_ASSET = "fades-of-fate-content-pack.zip"
PC_PROVENANCE_ASSET = "build_provenance-pc.json"
ANDROID_PROVENANCE_ASSET = "build_provenance-android.json"
SUMMARY_PROVENANCE_ASSET = "build_provenance.json"
GENERATION_RECEIPT = "data/chapter1_art_build.json"
EXCLUDED_CONTENT_PATHS = {"data/content-manifest.json"}
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


class ContentBuildError(RuntimeError):
    """Raised when canonical content cannot be packaged without ambiguity."""


_CANONICAL_TEXT_SUFFIXES = frozenset(
    {".cfg", ".ini", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
)


def _canonical_content_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() in _CANONICAL_TEXT_SUFFIXES:
        return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data


@dataclass(frozen=True)
class FileRecord:
    path: str
    sha256: str
    size: int


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentBuildError(f"JSON is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise ContentBuildError(f"JSON root must be an object: {path}")
    return payload


def _git(project_root: Path, *args: str, default: str = "unknown") -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return default
    return result.stdout.strip() or default


def _git_dirty(project_root: Path) -> bool:
    return bool(_git(project_root, "status", "--porcelain", default=""))


def _safe_relative(value: object, *, label: str) -> str:
    relative = str(value or "").replace("\\", "/").strip()
    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or ".." in pure.parts:
        raise ContentBuildError(f"{label} is not a safe project-relative path: {relative!r}")
    return pure.as_posix()


def _require_file(
    project_root: Path,
    value: object,
    *,
    label: str,
    prefix: str | None = None,
) -> Path:
    relative = _safe_relative(value, label=label)
    if prefix and not relative.startswith(prefix.rstrip("/") + "/"):
        raise ContentBuildError(f"{label} must stay under {prefix}: {relative}")
    path = (project_root / relative).resolve()
    if project_root not in path.parents or not path.is_file():
        raise ContentBuildError(f"{label} is missing or outside the project: {relative}")
    return path


def _campaign_level_ids(gameplay: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    campaign = gameplay.get("campaign", {})
    chapters = campaign.get("chapters", ()) if isinstance(campaign, Mapping) else ()
    if not isinstance(chapters, list):
        raise ContentBuildError("gameplay campaign chapters must be a list")
    for chapter in chapters:
        if not isinstance(chapter, Mapping) or not isinstance(chapter.get("levels"), list):
            raise ContentBuildError("each gameplay chapter must contain a levels list")
        for level in chapter["levels"]:
            if not isinstance(level, Mapping):
                raise ContentBuildError("each gameplay level must be an object")
            result.append(str(level.get("id", "")).strip())
    if not result or any(not value for value in result) or len(result) != len(set(result)):
        raise ContentBuildError("active gameplay level IDs must be present and unique")
    return result


def _verify_generation_receipt(project_root: Path) -> None:
    receipt_path = project_root / GENERATION_RECEIPT
    receipt = _read_json(receipt_path)
    if receipt.get("schema_version") != 1:
        raise ContentBuildError(f"unsupported Chapter 1 generation receipt: {receipt_path}")
    for section in ("inputs", "outputs"):
        records = receipt.get(section)
        if not isinstance(records, list) or not records:
            raise ContentBuildError(f"generation receipt {section} inventory is empty")
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                raise ContentBuildError(f"generation receipt {section}[{index}] must be an object")
            path = _require_file(
                project_root,
                record.get("path"),
                label=f"generation receipt {section}[{index}]",
            )
            expected_size = int(record.get("size", -1))
            expected_hash = str(record.get("sha256", "")).strip().lower()
            canonical_bytes = _canonical_content_bytes(path)
            if len(canonical_bytes) != expected_size or hashlib.sha256(canonical_bytes).hexdigest() != expected_hash:
                raise ContentBuildError(
                    f"Chapter 1 generated content is stale; rerun tools/build_chapter1_location_art.py: "
                    f"{path.relative_to(project_root)}"
                )


def validate_canonical_content(project_root: Path) -> dict[str, Any]:
    """Fail on duplicate levels, noncanonical assets, stale generation, or drift."""

    gameplay = _read_json(project_root / "data" / "gameplay.json")
    location = _read_json(project_root / "data" / "chapter1_location_lock.json")
    chunks = _read_json(project_root / "data" / "stage_chunks.json")
    gameplay_ids = _campaign_level_ids(gameplay)
    routes = location.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ContentBuildError("location manifest routes must be a non-empty list")
    route_ids = [str(route.get("level_id", "")).strip() for route in routes if isinstance(route, Mapping)]
    if route_ids != gameplay_ids or len(route_ids) != len(set(route_ids)):
        raise ContentBuildError(
            f"gameplay/location active level definitions differ: gameplay={gameplay_ids} routes={route_ids}"
        )

    active_assets: set[str] = set()
    vehicle_signatures: set[tuple[object, ...]] = set()
    vehicle_count = 0
    for route_index, route in enumerate(routes):
        if not isinstance(route, Mapping):
            raise ContentBuildError(f"location routes[{route_index}] must be an object")
        for field in SCENERY_FIELDS:
            path = _require_file(
                project_root,
                route.get(field),
                label=f"routes[{route_index}].{field}",
                prefix="assets/stage/chapter1_location_locked",
            )
            active_assets.add(path.relative_to(project_root).as_posix())
        physical = route.get("physical_scene_objects", ())
        if not isinstance(physical, list):
            raise ContentBuildError(f"routes[{route_index}].physical_scene_objects must be a list")
        for object_index, feature in enumerate(physical):
            if not isinstance(feature, Mapping):
                raise ContentBuildError("physical scene objects must be objects")
            path = _require_file(
                project_root,
                feature.get("asset"),
                label=f"routes[{route_index}].physical_scene_objects[{object_index}].asset",
                prefix="assets/props/vehicles",
            )
            active_assets.add(path.relative_to(project_root).as_posix())
            vehicle_count += 1
            vehicle_signatures.add(
                (
                    path.relative_to(project_root).as_posix(),
                    tuple(feature.get("paint_color", ())),
                    str(feature.get("condition", "")),
                    str(feature.get("accessory", "")),
                    int(feature.get("facing", 1)),
                )
            )
        forbidden = [key for key, value in route.items() if "fallback" in str(key).lower() and value]
        if forbidden:
            raise ContentBuildError(f"active route {route_ids[route_index]} declares fallback fields: {forbidden}")

    if vehicle_count < len(routes) or len(vehicle_signatures) != vehicle_count:
        raise ContentBuildError(
            f"parked vehicle variants must be route-specific and nonrepeating: "
            f"vehicles={vehicle_count} variants={len(vehicle_signatures)}"
        )

    chunk_routes = chunks.get("routes")
    if not isinstance(chunk_routes, list):
        raise ContentBuildError("stage_chunks.routes must be a list")
    chunk_ids = [str(route.get("level_id", "")).strip() for route in chunk_routes if isinstance(route, Mapping)]
    if chunk_ids != route_ids:
        raise ContentBuildError(f"generated stage chunk routes differ from active levels: {chunk_ids}")
    for route_index, route in enumerate(chunk_routes):
        if not isinstance(route, Mapping) or not isinstance(route.get("chunks"), list):
            raise ContentBuildError(f"stage_chunks.routes[{route_index}] is malformed")
        for chunk_index, chunk in enumerate(route["chunks"]):
            if not isinstance(chunk, Mapping):
                raise ContentBuildError("stage chunk records must be objects")
            _require_file(
                project_root,
                chunk.get("source_panel"),
                label=f"stage chunk source {route_index}:{chunk_index}",
                prefix="art_source/chapter1_location_locked/source_panels",
            )
            layers = chunk.get("layers")
            if not isinstance(layers, Mapping):
                raise ContentBuildError("stage chunk layers must be an object")
            for layer_name, layer in layers.items():
                if not isinstance(layer, Mapping):
                    raise ContentBuildError("stage chunk layer entries must be objects")
                path = _require_file(
                    project_root,
                    layer.get("asset"),
                    label=f"stage chunk {route_index}:{chunk_index}:{layer_name}",
                    prefix="assets/stage/chapter1_location_locked/chunks",
                )
                active_assets.add(path.relative_to(project_root).as_posix())

    _verify_generation_receipt(project_root)
    return {
        "level_ids": gameplay_ids,
        "active_assets": sorted(active_assets),
        "vehicle_variants": len(vehicle_signatures),
        "generation_receipt": GENERATION_RECEIPT,
    }


def _walk_content(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for folder in ("assets", "data"):
        root = project_root / folder
        if not root.is_dir():
            raise ContentBuildError(f"canonical content folder is missing: {root}")
        for path in root.rglob("*"):
            if path.is_file() and path.relative_to(project_root).as_posix() not in EXCLUDED_CONTENT_PATHS:
                files.append(path)
    return sorted(files, key=lambda path: path.relative_to(project_root).as_posix())


def _records(project_root: Path, files: Iterable[Path]) -> list[FileRecord]:
    records: list[FileRecord] = []
    for path in files:
        data = _canonical_content_bytes(path)
        records.append(
            FileRecord(
                path.relative_to(project_root).as_posix(),
                hashlib.sha256(data).hexdigest(),
                len(data),
            )
        )
    return records


def _build_deterministic_pack(
    project_root: Path,
    output: Path,
    records: Iterable[FileRecord],
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for record in records:
            info = zipfile.ZipInfo(record.path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info,
                _canonical_content_bytes(project_root / record.path),
                compresslevel=9,
            )


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _default_revision(project_root: Path) -> int:
    value = _git(project_root, "rev-list", "--count", "HEAD", default="1")
    try:
        return max(1, int(value))
    except ValueError:
        return 1


def build_release(
    project_root: Path,
    output_dir: Path,
    *,
    revision: int | None = None,
    version: str | None = None,
    strict: bool = False,
) -> dict[str, Path]:
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    validation = validate_canonical_content(project_root) if strict else {}
    files = _walk_content(project_root)
    records = _records(project_root, files)
    pack_path = output_dir / PACK_ASSET
    _build_deterministic_pack(project_root, pack_path, records)

    source_commit = _git(project_root, "rev-parse", "HEAD")
    generated_utc = _git(project_root, "show", "-s", "--format=%cI", "HEAD", default="unknown")
    content_revision = int(revision or _default_revision(project_root))
    content_version = str(version or VERSION)
    logical_identity = hashlib.sha256(
        json.dumps([asdict(record) for record in records], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema_version": 2,
        "content_version": content_version,
        "content_revision": content_revision,
        "minimum_game_version": content_version,
        "generated_utc": generated_utc,
        "source_commit": source_commit,
        "source_dirty": _git_dirty(project_root),
        "platforms": ["pc", "android"],
        "logical_content_sha256": logical_identity,
        "pack": {
            "asset": PACK_ASSET,
            "sha256": sha256_path(pack_path),
            "size": pack_path.stat().st_size,
        },
        "files": [asdict(record) for record in records],
        "strict_validation": validation,
    }
    manifest_bytes = _json_bytes(manifest)
    paths = {
        "manifest": output_dir / MANIFEST_ASSET,
        "pc_manifest": output_dir / PC_MANIFEST_ASSET,
        "android_manifest": output_dir / ANDROID_MANIFEST_ASSET,
        "pack": pack_path,
        "pc_provenance": output_dir / PC_PROVENANCE_ASSET,
        "android_provenance": output_dir / ANDROID_PROVENANCE_ASSET,
        "provenance": output_dir / SUMMARY_PROVENANCE_ASSET,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in ("manifest", "pc_manifest", "android_manifest"):
        paths[key].write_bytes(manifest_bytes)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    for platform, key in (("pc", "pc_provenance"), ("android", "android_provenance")):
        write_provenance(
            paths[key],
            build_artifact_provenance(
                project_root,
                platform=platform,
                game_version=content_version,
                content_revision=content_revision,
                content_manifest_sha256=manifest_hash,
                content_pack_sha256=manifest["pack"]["sha256"],
                content_pack_size=manifest["pack"]["size"],
                build_timestamp=generated_utc,
                source_commit=source_commit,
            ),
        )
    write_provenance(
        paths["provenance"],
        {
            "schema_version": 1,
            "platform": "both",
            "build_timestamp": generated_utc,
            "game_version": content_version,
            "game_git_commit": source_commit,
            "content_git_commit": source_commit,
            "content_revision": content_revision,
            "content_manifest_sha256": manifest_hash,
            "content_pack_sha256": manifest["pack"]["sha256"],
            "pc_provenance": PC_PROVENANCE_ASSET,
            "android_provenance": ANDROID_PROVENANCE_ASSET,
        },
    )
    verify_release(paths["manifest"])
    return paths


def verify_release(manifest_path: Path) -> None:
    manifest_path = manifest_path.resolve()
    output_dir = manifest_path.parent
    manifest_bytes = manifest_path.read_bytes()
    for alias in (output_dir / PC_MANIFEST_ASSET, output_dir / ANDROID_MANIFEST_ASSET):
        if alias.read_bytes() != manifest_bytes:
            raise ContentBuildError(f"PC/Android manifest identity drift: {alias}")
    manifest = _read_json(manifest_path)
    pack = manifest.get("pack")
    if not isinstance(pack, Mapping):
        raise ContentBuildError("manifest pack metadata is missing")
    pack_path = output_dir / str(pack.get("asset", ""))
    if not pack_path.is_file() or pack_path.stat().st_size != int(pack.get("size", -1)):
        raise ContentBuildError("content pack size/path mismatch")
    if sha256_path(pack_path) != str(pack.get("sha256", "")):
        raise ContentBuildError("content pack hash mismatch")
    expected = {str(record["path"]): record for record in manifest.get("files", ())}
    with zipfile.ZipFile(pack_path, "r") as archive:
        if archive.namelist() != sorted(expected):
            raise ContentBuildError("content pack file list differs from the manifest")
        for name, record in expected.items():
            data = archive.read(name)
            if len(data) != int(record["size"]) or hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ContentBuildError(f"content pack file mismatch: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--output-dir", default="dist/content")
    parser.add_argument("--content-revision", type=int, default=None)
    parser.add_argument("--content-version", default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--verify-only", default=None, help="verify an existing manifest")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if args.verify_only:
        verify_release(Path(args.verify_only))
        print(f"VERIFIED={Path(args.verify_only).resolve()}")
        return
    output = Path(args.output_dir)
    if not output.is_absolute():
        output = project_root / output
    paths = build_release(
        project_root,
        output,
        revision=args.content_revision,
        version=args.content_version,
        strict=args.strict,
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
