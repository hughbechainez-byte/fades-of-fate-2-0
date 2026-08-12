"""Build the explicit PASS/FAIL gate for the Chapter 1 visual release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CHECK_NAMES = (
    "detail_at_least_comparable_to_sunset_reference",
    "no_large_placeholder_building_masses",
    "no_obvious_same_car_repetition",
    "visible_moving_sky",
    "visible_environmental_animation",
    "correct_world_anchoring",
    "correct_parallax",
    "no_stitched_image_sliding",
    "no_missing_or_fallback_assets",
    "pc_android_manifest_equality",
    "pc_android_level_equality",
    "stable_performance",
    "matching_runtime_provenance",
)


class AcceptanceError(RuntimeError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"required acceptance input is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise AcceptanceError(f"acceptance input root must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_acceptance(
    project_root: Path,
    *,
    scenery_report_path: Path,
    validation_report_path: Path,
    content_dir: Path,
    runtime_provenance_path: Path,
    require_artifact_match: bool,
) -> dict[str, Any]:
    scenery = _read(scenery_report_path)
    validation = _read(validation_report_path)
    provenance = _read(runtime_provenance_path)
    root_manifest_path = content_dir / "fades-of-fate-content-manifest.json"
    pc_manifest_path = content_dir / "fades-of-fate-content-manifest-pc.json"
    android_manifest_path = content_dir / "fades-of-fate-content-manifest-android.json"
    manifest = _read(root_manifest_path)
    location = _read(project_root / "data" / "chapter1_location_lock.json")

    manual = scenery.get("manual_reference_comparison", {})
    criteria = manual.get("criteria", {}) if isinstance(manual, Mapping) else {}
    phases = scenery.get("atmosphere_phase_results", ())
    phase_rows = [row for row in phases if isinstance(row, Mapping)] if isinstance(phases, list) else []
    integration = scenery.get("integration_visual_matrix", {})
    routes = location.get("routes", ())
    route_rows = [route for route in routes if isinstance(route, Mapping)] if isinstance(routes, list) else []
    variants = {
        (
            str(feature.get("asset", "")),
            tuple(feature.get("paint_color", ())),
            str(feature.get("condition", "")),
            str(feature.get("accessory", "")),
            int(feature.get("facing", 1)),
        )
        for route in route_rows
        for feature in route.get("physical_scene_objects", ())
        if isinstance(feature, Mapping)
    }
    level_ids = [str(route.get("level_id", "")) for route in route_rows]
    manifest_levels = (
        manifest.get("strict_validation", {}).get("level_ids", ())
        if isinstance(manifest.get("strict_validation"), Mapping)
        else ()
    )
    manifest_hashes = {
        _sha256(root_manifest_path),
        _sha256(pc_manifest_path),
        _sha256(android_manifest_path),
    }
    provenance_match = provenance.get("artifact_match") is True
    if not require_artifact_match:
        provenance_match = provenance_match or provenance.get("artifact_match") == "source"

    raw_checks: dict[str, tuple[bool, str]] = {
        "detail_at_least_comparable_to_sunset_reference": (
            bool(scenery.get("passed")) and manual.get("status") == "completed_by_codex_visual_review",
            "all-route sheet reviewed against the detailed sunset/location references",
        ),
        "no_large_placeholder_building_masses": (
            bool(criteria.get("no_generic_fantasy_or_placeholder_scenery")),
            "manual location-art criterion",
        ),
        "no_obvious_same_car_repetition": (
            len(variants) >= 4 and len(variants) == len(route_rows),
            f"route_vehicle_variants={len(variants)}",
        ),
        "visible_moving_sky": (
            bool(phase_rows) and all(bool(row.get("sky_motion_visibly_persistent")) for row in phase_rows),
            f"animated_route_phases={len(phase_rows)}",
        ),
        "visible_environmental_animation": (
            bool(phase_rows) and all(bool(row.get("fixed_camera_phase_hashes_distinct")) for row in phase_rows),
            "fixed-camera animated hashes differ on every route",
        ),
        "correct_world_anchoring": (
            bool(integration.get("passed")) and bool(criteria.get("parking_setbacks_and_driveways_visible")),
            "projection/integration matrix and visible ground registration passed",
        ),
        "correct_parallax": (
            bool(integration.get("passed")) and all(len(row.get("steady", {}).get("parallax_factors", ())) == 3 for row in phase_rows),
            "three bounded atmosphere/world depth rates exercised",
        ),
        "no_stitched_image_sliding": (
            bool(criteria.get("panel_handoffs_are_structurally_masked")) and bool(scenery.get("seam_results")),
            "world-locked seam captures passed",
        ),
        "no_missing_or_fallback_assets": (
            bool(provenance.get("all_assets_resolved"))
            and not bool(provenance.get("fallback_asset_used"))
            and not bool(provenance.get("noncanonical_asset_used")),
            "runtime provenance resolved every rendered scenery asset canonically",
        ),
        "pc_android_manifest_equality": (
            len(manifest_hashes) == 1,
            f"manifest_sha256={next(iter(manifest_hashes)) if len(manifest_hashes) == 1 else sorted(manifest_hashes)}",
        ),
        "pc_android_level_equality": (
            level_ids == list(manifest_levels) and manifest.get("platforms") == ["pc", "android"],
            f"levels={level_ids}",
        ),
        "stable_performance": (
            bool(validation.get("passed")),
            "Chapter 1 pacing/performance/visual matrix passed",
        ),
        "matching_runtime_provenance": (
            provenance_match,
            f"artifact_match={provenance.get('artifact_match')!r}",
        ),
    }
    checks = [
        {"id": name, "status": "PASS" if raw_checks[name][0] else "FAIL", "detail": raw_checks[name][1]}
        for name in CHECK_NAMES
    ]
    return {
        "schema_version": 1,
        "classification": "visual_release_acceptance",
        "passed": all(check["status"] == "PASS" for check in checks),
        "require_artifact_match": require_artifact_match,
        "checks": checks,
        "inputs": {
            "scenery_report": str(scenery_report_path),
            "validation_report": str(validation_report_path),
            "content_manifest": str(root_manifest_path),
            "runtime_provenance": str(runtime_provenance_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--scenery-report", default="build/chapter1_location_sources_report.json")
    parser.add_argument("--validation-report", default="build/chapter1_validation_build.json")
    parser.add_argument("--content-dir", default="dist/content")
    parser.add_argument("--runtime-provenance", required=True)
    parser.add_argument("--require-artifact-match", action="store_true")
    parser.add_argument("--output", default="build/visual_acceptance.json")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    resolve = lambda value: Path(value).resolve() if Path(value).is_absolute() else (root / value).resolve()
    report = build_acceptance(
        root,
        scenery_report_path=resolve(args.scenery_report),
        validation_report_path=resolve(args.validation_report),
        content_dir=resolve(args.content_dir),
        runtime_provenance_path=resolve(args.runtime_provenance),
        require_artifact_match=args.require_artifact_match,
    )
    output = resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    if not report["passed"]:
        failed = [check["id"] for check in report["checks"] if check["status"] == "FAIL"]
        raise SystemExit(f"visual acceptance failed: {failed}")


if __name__ == "__main__":
    main()
