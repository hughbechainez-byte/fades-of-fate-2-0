"""Validate production entity art, routing, and packaged-gameplay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_openbor_pose_evidence as pose_evidence

PRODUCTION_GLOB = "content/characters/*/metadata/production_manifest.json"
CLIP_UNIQUE_FLOORS = {
    "idle": 8,
    "walk": 12,
    "transition": 4,
    "light_attack": 8,
    "heavy_attack": 10,
    "special": 14,
    "light_pain": 5,
    "heavy_pain": 7,
    "knockdown": 8,
    "down": 6,
    "rise": 8,
    "jump_start": 4,
    "airborne": 6,
    "landing": 4,
    "air_attack": 8,
    "dodge": 8,
    "block": 3,
    "block_impact": 2,
    "interaction": 8,
    "death": 10,
    "spawn": 5,
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def palette_bytes(image: Image.Image) -> bytes:
    palette = image.getpalette()
    if palette is None:
        raise ValueError("indexed image has no palette")
    return bytes((palette + [0] * 768)[:768])


def alpha_mask(image: Image.Image) -> tuple[frozenset[tuple[int, int]], tuple[int, int, int, int]]:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if set(alpha.getdata()) - {0, 255}:
        raise ValueError("sprite alpha must be hard 0/255")
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError("sprite is empty")
    pixels = alpha.load()
    points = frozenset((x, y) for y in range(alpha.height) for x in range(alpha.width) if pixels[x, y])
    return points, bounds


def normalized_mask_hash(points: frozenset[tuple[int, int]], bounds: tuple[int, int, int, int]) -> str:
    left, top, right, bottom = bounds
    width, height = right - left, bottom - top
    normalized = bytearray(width * height)
    for x, y in points:
        normalized[(y - top) * width + (x - left)] = 1
    return sha256_bytes(width.to_bytes(2, "big") + height.to_bytes(2, "big") + bytes(normalized))


def iou(a: frozenset[tuple[int, int]], b: frozenset[tuple[int, int]]) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 1.0


def reviewed_pairs(art: dict) -> dict[frozenset[str], dict]:
    result: dict[frozenset[str], dict] = {}
    for review in art.get("near_duplicate_reviews", []):
        key = frozenset((review.get("pose_a", ""), review.get("pose_b", "")))
        if len(key) == 2 and review.get("meaningful_difference") and review.get("reviewer"):
            result[key] = review
    return result


def validate_design(path: Path, design: dict) -> None:
    target = int(design["exact_unique_pose_target"])
    allocation = {key: int(value) for key, value in design["pose_allocation"].items()}
    if sum(allocation.values()) != target:
        raise ValueError(f"{path}: pose allocation {sum(allocation.values())} != exact target {target}")
    if design.get("maturity") != "production":
        raise ValueError(f"{path}: production validation requires maturity=production")
    if design.get("entity_class") not in {"playable_hero", "basic_enemy", "elite_enemy", "boss"}:
        raise ValueError(f"{path}: invalid entity_class")
    if not design.get("state_inventory", {}).get("required"):
        raise ValueError(f"{path}: required state inventory is empty")
    for action in design.get("actions", []):
        if not action.get("id") or not action.get("trigger") or not action.get("native_animation"):
            raise ValueError(f"{path}: every action needs id, trigger, and native_animation")


def _require_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ValueError(f"runtime evidence {label} mismatch: {actual!r} != {expected!r}")


def _require_unique(values: list[object], label: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"runtime evidence reuses {label}")


def _capture_geometry(method: str) -> tuple[list[int], list[int] | None, str]:
    if method == pose_evidence.METHOD_NATIVE_F12:
        return list(pose_evidence.EXPECTED_SIZE), None, pose_evidence.NORMALIZATION_NONE
    if method == pose_evidence.METHOD_CLIENT_NORMALIZED:
        return (
            list(pose_evidence.OBSERVED_CLIENT_SIZE),
            list(pose_evidence.OBSERVED_CLIENT_SIZE),
            pose_evidence.NORMALIZATION_NEAREST,
        )
    if method == pose_evidence.METHOD_CLIENT_EXACT:
        return (
            list(pose_evidence.EXPECTED_SIZE),
            list(pose_evidence.EXPECTED_SIZE),
            pose_evidence.NORMALIZATION_NONE,
        )
    raise ValueError(f"runtime evidence has unsupported capture method {method!r}")


def self_test_runtime_evidence_guards() -> dict:
    rejected = []
    for label, values in (("record path", ["a", "a"]), ("screenshot path", ["a.png", "a.png"]), ("screenshot hash", ["f" * 64, "f" * 64])):
        try:
            _require_unique(values, label)
        except ValueError:
            rejected.append(label)
        else:
            raise AssertionError(f"synthetic duplicate {label} was accepted")
    fallback = _capture_geometry(pose_evidence.METHOD_CLIENT_NORMALIZED)
    if fallback != ([960, 540], [960, 540], pose_evidence.NORMALIZATION_NEAREST):
        raise AssertionError(f"fallback geometry contract drifted: {fallback}")
    exact_fallback = _capture_geometry(pose_evidence.METHOD_CLIENT_EXACT)
    if exact_fallback != ([640, 360], [640, 360], pose_evidence.NORMALIZATION_NONE):
        raise AssertionError(f"exact fallback geometry contract drifted: {exact_fallback}")
    try:
        _capture_geometry("Build 7949 native F12 framebuffer PNG")
    except ValueError:
        ambiguous_native_label_rejected = True
    else:
        raise AssertionError("ambiguous legacy native label was accepted")
    return {
        "status": "pass",
        "synthetic_duplicate_rejections": rejected,
        "fallback_geometry_verified": True,
        "ambiguous_native_label_rejected": ambiguous_native_label_rejected,
    }


def validate_runtime_evidence(summary_path: Path) -> dict[str, set[str]]:
    if not summary_path.is_file():
        raise ValueError(f"runtime evidence summary is missing: {summary_path}")
    summary = load_json(summary_path)
    _require_equal(summary.get("schema_version"), 2, "schema_version")
    _require_equal(summary.get("evidence_kind"), "openbor_build7949_all_pose_capture_run", "kind")
    _require_equal(summary.get("status"), "pass", "status")
    _require_equal(summary.get("pose_count"), pose_evidence.EXPECTED_TOTAL, "pose_count")
    _require_equal(summary.get("entity_counts"), pose_evidence.ENTITY_COUNTS, "entity_counts")
    _require_equal(summary.get("capture_contract"), pose_evidence.capture_contract(), "capture_contract")
    method = summary.get("capture_method")
    expected_source_size, expected_observed_size, expected_normalization = _capture_geometry(method)
    method_selection = summary.get("method_selection", {})
    _require_equal(method_selection.get("preferred"), pose_evidence.METHOD_NATIVE_F12, "preferred capture method")
    _require_equal(method_selection.get("selected"), method, "selected capture method")
    native_probe = method_selection.get("native_f12_probe")
    if method == pose_evidence.METHOD_NATIVE_F12:
        _require_equal(native_probe, "valid_native_f12_png", "native F12 probe")
    elif not isinstance(native_probe, str) or native_probe == "valid_native_f12_png":
        raise ValueError("normalized client fallback lacks a failed native F12 probe")

    templates = pose_evidence.build_schedule()
    package = summary.get("package", {})
    _require_equal(package.get("engine_build"), 7949, "engine build")
    package_manifest_path = pose_evidence.resolve_repo_path(package.get("package_manifest_path", ""))
    if sha256(package_manifest_path) != package.get("package_manifest_sha256"):
        raise ValueError("runtime evidence package manifest hash is stale")
    package_manifest = load_json(package_manifest_path)
    _require_equal(package_manifest.get("schema_version"), 2, "package manifest schema")
    _require_equal(package_manifest.get("engine_build"), 7949, "package manifest engine build")
    _require_equal(package.get("engine_reported_commit"), package_manifest.get("engine_reported_commit"), "engine commit")
    package_files = package_manifest.get("files", [])
    if len(package_files) != int(package_manifest.get("file_count", -1)):
        raise ValueError("runtime evidence package file count is inconsistent")
    package_file_hashes = {item["path"]: item["sha256"] for item in package_files}
    if len(package_file_hashes) != len(package_files):
        raise ValueError("runtime evidence package manifest contains duplicate paths")
    _require_equal(package.get("pak_file_count"), len(package_files), "PAK file count")
    provenance = package_manifest.get("pose_showcase_provenance", {})
    _require_equal(provenance.get("pose_count"), pose_evidence.EXPECTED_TOTAL, "package pose count")
    _require_equal(provenance.get("baseline_index"), pose_evidence.BASELINE_INDEX, "package baseline index")
    schedule_fact = provenance.get("black_dave_schedule", {})
    schedule_path = pose_evidence.resolve_repo_path(schedule_fact.get("path", ""))
    if not schedule_path.is_file() or sha256(schedule_path) != schedule_fact.get("sha256"):
        raise ValueError("runtime evidence Black Dave QA schedule provenance is stale")
    for manifest_key, local_value, package_value in (
        ("harness_sha256", "openbor/data/scripts/entity_tech_demo.c", "data/scripts/entity_tech_demo.c"),
        ("overlay_sha256", "openbor/data/scripts/entity_pose_overlay.c", "data/scripts/entity_pose_overlay.c"),
    ):
        local_path = ROOT / local_value
        expected_hash = provenance.get(manifest_key)
        if not local_path.is_file() or sha256(local_path) != expected_hash or package_file_hashes.get(package_value) != expected_hash:
            raise ValueError(f"runtime evidence {manifest_key} provenance is stale")
    pak = pose_evidence.resolve_repo_path(package.get("pak_path", ""))
    exe = pose_evidence.resolve_repo_path(package.get("exe_path", ""))
    for path, expected_hash, expected_size, label in (
        (pak, package.get("pak_sha256"), package.get("pak_size"), "PAK"),
        (exe, package.get("exe_sha256"), package.get("exe_size"), "OpenBOR executable"),
    ):
        if not path.is_file() or sha256(path) != expected_hash or path.stat().st_size != int(expected_size or -1):
            raise ValueError(f"runtime evidence {label} hash/size is stale")
    _require_equal(package.get("pak_sha256"), package_manifest.get("sha256"), "PAK manifest hash")
    _require_equal(package.get("pak_size"), package_manifest.get("size"), "PAK manifest size")
    runtime_exe = package_manifest.get("runtime_executable", {})
    _require_equal(package.get("exe_sha256"), runtime_exe.get("sha256"), "executable manifest hash")
    _require_equal(package.get("exe_size"), runtime_exe.get("size"), "executable manifest size")

    baseline = summary.get("baseline", {})
    baseline_path = pose_evidence.resolve_repo_path(baseline.get("path", ""))
    if not baseline_path.is_file() or sha256(baseline_path) != baseline.get("sha256"):
        raise ValueError("runtime evidence baseline is absent or stale")
    with Image.open(baseline_path) as source:
        baseline_image = source.convert("RGB")
    _require_equal(baseline_image.size, pose_evidence.EXPECTED_SIZE, "baseline size")
    baseline_marker = pose_evidence.decode_barcode(baseline_image)
    _require_equal(baseline_marker["index"], pose_evidence.BASELINE_INDEX, "baseline marker")
    _require_equal(baseline.get("decoded_index"), baseline_marker["index"], "recorded baseline marker")
    _require_equal(baseline.get("barcode_bits"), baseline_marker["bits"], "recorded baseline bits")
    _require_equal(baseline.get("width"), pose_evidence.EXPECTED_SIZE[0], "baseline width")
    _require_equal(baseline.get("height"), pose_evidence.EXPECTED_SIZE[1], "baseline height")
    _require_equal(baseline.get("method"), method, "baseline capture method")
    if int(baseline.get("stable_marker_polls", 0)) < 2:
        raise ValueError("runtime evidence baseline marker was not stable for two polls")
    _require_equal(baseline.get("source_size"), expected_source_size, "baseline source size")
    _require_equal(baseline.get("observed_client_size"), expected_observed_size, "baseline observed client size")
    _require_equal(baseline.get("normalization"), expected_normalization, "baseline normalization")

    entries = summary.get("records", [])
    _require_equal(len(entries), pose_evidence.EXPECTED_TOTAL, "record count")
    expected_indexes = list(range(pose_evidence.EXPECTED_TOTAL))
    _require_equal([item.get("global_index") for item in entries], expected_indexes, "record index order")
    _require_equal([item.get("pose_id") for item in entries], [item.pose_id for item in templates], "record pose order")
    record_paths = [item.get("path") for item in entries]
    _require_unique(record_paths, "record path")
    digest = sha256_bytes(
        "".join(f"{item['global_index']}:{item['pose_id']}:{item['sha256']}\n" for item in entries).encode("ascii")
    )
    _require_equal(summary.get("records_digest_sha256"), digest, "records digest")

    screenshot_paths: set[str] = set()
    screenshot_hashes: set[str] = set()
    by_entity: dict[str, set[str]] = defaultdict(set)
    run_id = summary.get("run_id")
    for template, entry in zip(templates, entries, strict=True):
        record_path = pose_evidence.resolve_repo_path(entry["path"])
        if not record_path.is_file() or sha256(record_path) != entry.get("sha256"):
            raise ValueError(f"runtime evidence record is absent or stale: {entry['path']}")
        record = load_json(record_path)
        _require_equal(record.get("schema_version"), 2, f"{template.pose_id} record schema")
        _require_equal(record.get("evidence_kind"), "openbor_build7949_pose_capture", f"{template.pose_id} kind")
        _require_equal(record.get("run_id"), run_id, f"{template.pose_id} run_id")
        _require_equal(record.get("status"), "pass", f"{template.pose_id} status")
        for key, expected in (
            ("global_index", template.global_index), ("entity", template.entity), ("pose_id", template.pose_id),
            ("group", template.group), ("model_animation", template.model_animation),
            ("animation_constant", template.animation_constant), ("frame_index", template.frame_index),
            ("hold_ticks", template.hold_ticks),
        ):
            _require_equal(record.get(key), expected, f"{template.pose_id} {key}")
        _require_equal(record.get("package"), package, f"{template.pose_id} package identity")
        _require_equal(record.get("baseline"), baseline, f"{template.pose_id} baseline identity")
        expected_source = {
            "path": template.source_path, "generated_path": template.generated_path,
            "sha256": template.sprite_sha256, "palette_sha256": template.palette_sha256,
            "opaque_mask_sha256": template.opaque_mask_sha256, "opaque_pixels": template.opaque_pixels,
        }
        _require_equal(record.get("source"), expected_source, f"{template.pose_id} source identity")
        generated_package_path = template.generated_path.removeprefix("openbor/")
        _require_equal(package_file_hashes.get(generated_package_path), template.sprite_sha256, f"{template.pose_id} packaged sprite")

        capture = record.get("capture", {})
        screenshot_value = capture.get("path", "")
        if screenshot_value in screenshot_paths:
            raise ValueError(f"runtime evidence reuses screenshot path {screenshot_value}")
        screenshot_paths.add(screenshot_value)
        screenshot_path = pose_evidence.resolve_repo_path(screenshot_value)
        screenshot_hash = sha256(screenshot_path) if screenshot_path.is_file() else None
        _require_equal(screenshot_hash, capture.get("sha256"), f"{template.pose_id} screenshot hash")
        if screenshot_hash in screenshot_hashes:
            raise ValueError(f"runtime evidence reuses screenshot content hash {screenshot_hash}")
        screenshot_hashes.add(screenshot_hash)
        with Image.open(screenshot_path) as source:
            screenshot = source.convert("RGB")
        _require_equal(screenshot.size, pose_evidence.EXPECTED_SIZE, f"{template.pose_id} screenshot size")
        decoded = pose_evidence.decode_barcode(screenshot)
        _require_equal(decoded["index"], template.global_index, f"{template.pose_id} decoded marker")
        for key, expected in (
            ("width", pose_evidence.EXPECTED_SIZE[0]), ("height", pose_evidence.EXPECTED_SIZE[1]),
            ("method", method), ("source_size", expected_source_size),
            ("observed_client_size", expected_observed_size), ("normalization", expected_normalization),
            ("marker_source", "level updatedscript after entity queue at hud_z+100"),
            ("decoded_index", template.global_index), ("barcode_bits", decoded["bits"]),
            ("barcode_parity", decoded["parity"]), ("screen_root", list(pose_evidence.SCREEN_ROOT)),
            ("model_root", list(pose_evidence.MODEL_ROOT)), ("direction", pose_evidence.DIRECTION),
            ("roi", list(pose_evidence.ROI)),
        ):
            _require_equal(capture.get(key), expected, f"{template.pose_id} capture {key}")
        if int(capture.get("stable_marker_polls", 0)) < 2:
            raise ValueError(f"runtime evidence marker was not stable for {template.pose_id}")
        analysis = pose_evidence.analyze_capture(screenshot, baseline_image, template, templates)
        for key, expected in analysis.items():
            _require_equal(capture.get(key), expected, f"{template.pose_id} recomputed {key}")
        if analysis["status"] != "pass":
            raise ValueError(f"runtime evidence visual gate failed for {template.pose_id}: {analysis['failures']}")
        by_entity[template.entity].add(template.pose_id)

    contact = summary.get("contact_sheet", {})
    contact_path = pose_evidence.resolve_repo_path(contact.get("path", ""))
    if not contact_path.is_file() or sha256(contact_path) != contact.get("sha256"):
        raise ValueError("runtime evidence contact sheet is absent or stale")
    if baseline.get("sha256") in screenshot_hashes:
        raise ValueError("runtime evidence reuses the entity-free baseline as a pose screenshot")
    return dict(by_entity)


def validate_entity(design_path: Path, stage: str, near_threshold: float, runtime_evidence: dict[str, set[str]] | None = None) -> dict:
    design = load_json(design_path)
    validate_design(design_path, design)
    entity_id = design["entity_id"]
    art_path = design_path.parents[1] / "sprites" / "pose_manifest.json"
    if not art_path.is_file():
        raise ValueError(f"{art_path}: required authored-pose manifest is missing")
    art = load_json(art_path)
    if art.get("entity_id") != entity_id:
        raise ValueError(f"{art_path}: entity_id mismatch")
    target = int(design["exact_unique_pose_target"])
    poses = art.get("poses", [])
    if len(poses) != target:
        raise ValueError(f"{art_path}: {len(poses)} pose records != exact target {target}")
    pose_ids = [pose.get("id") for pose in poses]
    if None in pose_ids or len(set(pose_ids)) != target:
        raise ValueError(f"{art_path}: pose IDs must be present and globally unique")
    allocation = {key: int(value) for key, value in design["pose_allocation"].items()}
    actual_groups = Counter(pose.get("group") for pose in poses)
    if actual_groups != Counter(allocation):
        raise ValueError(f"{art_path}: pose groups {dict(actual_groups)} != allocation {allocation}")
    clips = art.get("clips", {})
    if not clips:
        raise ValueError(f"{art_path}: clip table is empty")
    referenced = set()
    for clip_id, clip in clips.items():
        sequence = clip.get("pose_ids", [])
        if not sequence or any(pose_id not in set(pose_ids) for pose_id in sequence):
            raise ValueError(f"{art_path}: clip {clip_id} has missing or invalid pose references")
        action_type = clip.get("action_type")
        floor = CLIP_UNIQUE_FLOORS.get(action_type)
        if floor is None:
            raise ValueError(f"{art_path}: clip {clip_id} has unsupported action_type {action_type!r}")
        if len(set(sequence)) < floor:
            raise ValueError(f"{art_path}: clip {clip_id} has {len(set(sequence))} unique poses; {action_type} requires {floor}")
        if not clip.get("trigger") or not clip.get("native_animation"):
            raise ValueError(f"{art_path}: clip {clip_id} lacks trigger/native animation")
        referenced.update(sequence)
    if referenced != set(pose_ids):
        missing = sorted(set(pose_ids) - referenced)
        raise ValueError(f"{art_path}: unreferenced pose IDs, first={missing[:8]}")

    expected_canvas = tuple(design["canvas"])
    expected_root = list(design["root_offset"])
    rgba_groups: dict[str, list[str]] = defaultdict(list)
    alpha_groups: dict[str, list[str]] = defaultdict(list)
    normalized_groups: dict[str, list[str]] = defaultdict(list)
    masks: dict[str, frozenset[tuple[int, int]]] = {}
    palettes: dict[str, list[str]] = defaultdict(list)
    for pose in poses:
        pose_id = pose["id"]
        if pose.get("approved") is not True:
            raise ValueError(f"{art_path}: {pose_id} is not approved")
        if pose.get("root") != expected_root:
            raise ValueError(f"{art_path}: {pose_id} root {pose.get('root')} != {expected_root}")
        if not pose.get("clips") or not pose.get("actions"):
            raise ValueError(f"{art_path}: {pose_id} lacks clip/action reachability records")
        sprite = ROOT / pose["path"]
        if not sprite.is_file():
            raise ValueError(f"{art_path}: missing sprite {sprite}")
        image = Image.open(sprite)
        if image.mode != "P" or image.size != expected_canvas or image.info.get("transparency") != 0:
            raise ValueError(f"{sprite}: expected indexed {expected_canvas} sprite with transparency index 0")
        palette_hash = sha256_bytes(palette_bytes(image))
        palettes[palette_hash].append(pose_id)
        points, bounds = alpha_mask(image)
        masks[pose_id] = points
        rgba_groups[sha256_bytes(image.convert("RGBA").tobytes())].append(pose_id)
        alpha_groups[sha256_bytes(image.convert("RGBA").getchannel("A").tobytes())].append(pose_id)
        normalized_groups[normalized_mask_hash(points, bounds)].append(pose_id)
        recorded_bounds = pose.get("body_bounds")
        if recorded_bounds != list(bounds):
            raise ValueError(f"{art_path}: {pose_id} recorded bounds {recorded_bounds} != {list(bounds)}")
    if len(palettes) != 1:
        raise ValueError(f"{art_path}: model palette drift across {len(palettes)} palettes")

    reviews = reviewed_pairs(art)
    for label, groups in (("RGBA", rgba_groups), ("root alpha", alpha_groups), ("translation-normalized alpha", normalized_groups)):
        for group in groups.values():
            if len(group) > 1:
                raise ValueError(f"{art_path}: exact {label} duplicate group {sorted(group)[:8]}")

    near_pairs: list[tuple[str, str, float]] = []
    sorted_ids = sorted(masks)
    for index, pose_a in enumerate(sorted_ids):
        for pose_b in sorted_ids[index + 1 :]:
            score = iou(masks[pose_a], masks[pose_b])
            if score >= near_threshold and frozenset((pose_a, pose_b)) not in reviews:
                near_pairs.append((pose_a, pose_b, round(score, 6)))
    if near_pairs:
        raise ValueError(f"{art_path}: unresolved near-duplicate silhouettes, first={near_pairs[:8]}")

    if stage in {"implementation", "runtime"}:
        model_path = ROOT / art.get("runtime", {}).get("model", "")
        if not model_path.is_file():
            raise ValueError(f"{art_path}: runtime model is missing")
        model_text = model_path.read_text(encoding="utf-8", errors="strict")
        evidence_ids = set()
        for pose in poses:
            if pose.get("runtime_reachable") is not True:
                raise ValueError(f"{art_path}: {pose['id']} is not runtime reachable")
            generated = pose.get("generated_path")
            model_reference = generated.removeprefix("openbor/") if generated else ""
            if not generated or not (ROOT / generated).is_file() or model_reference not in model_text:
                raise ValueError(f"{art_path}: {pose['id']} generated frame is absent from model")
    if stage == "runtime":
        evidence_ids = (runtime_evidence or {}).get(entity_id, set())
        if evidence_ids != set(pose_ids):
            raise ValueError(f"{art_path}: visible gameplay pose coverage is incomplete")

    return {
        "entity": entity_id,
        "target": target,
        "unique_approved": len(poses),
        "unique_referenced": len(referenced),
        "unique_runtime_reachable": target if stage in {"implementation", "runtime"} else None,
        "unique_visibly_exercised": target if stage == "runtime" else None,
        "palette_sha256": next(iter(palettes)),
        "near_duplicate_threshold": near_threshold,
        "status": "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("art", "implementation", "runtime"), default="art")
    parser.add_argument("--entity", action="append", default=[])
    parser.add_argument("--near-threshold", type=float, default=0.9975)
    parser.add_argument("--evidence-summary", type=Path, default=Path("build/entity_pose_evidence/summary.json"))
    parser.add_argument("--self-test-runtime-evidence", action="store_true")
    args = parser.parse_args()
    if args.self_test_runtime_evidence:
        print(json.dumps(self_test_runtime_evidence_guards(), indent=2))
        return 0
    design_paths = sorted(ROOT.glob(PRODUCTION_GLOB))
    if args.entity:
        requested = set(args.entity)
        design_paths = [path for path in design_paths if path.parents[1].name in requested]
        missing = requested - {path.parents[1].name for path in design_paths}
        if missing:
            raise SystemExit(f"unknown production entities: {sorted(missing)}")
    if not design_paths:
        raise SystemExit("no production entity manifests found")
    runtime_evidence = validate_runtime_evidence((ROOT / args.evidence_summary).resolve()) if args.stage == "runtime" else None
    reports = [validate_entity(path, args.stage, args.near_threshold, runtime_evidence) for path in design_paths]
    print(json.dumps({"status": "pass", "stage": args.stage, "entities": reports}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
