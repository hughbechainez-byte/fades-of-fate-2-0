"""Build a dependency-clean native OpenBOR PACK v0 tech-demo module."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT_FILES = (
    "levels.txt",
    "lifebar.txt",
    "models.txt",
    "pal.act",
    "script.txt",
    "video.txt",
)
RUNTIME_FILES = (
    "chars/black_dave/black_dave.txt",
    "chars/black_dave/black_dave_flame_fx.txt",
    "chars/black_dave/black_dave_flame_shot.txt",
    "chars/black_dave/black_dave_impact_fx.txt",
    "chars/homeless_man/homeless_man.txt",
    "chars/police_officer/police_officer.txt",
    "levels/entity_combat_tech_demo.txt",
    "levels/i8_underpass/panels/underpass_a.png",
    "levels/i8_underpass/panels/underpass_b.png",
    "levels/i8_underpass/panels/underpass_c.png",
    "levels/i8_underpass/panels/underpass_d.png",
    "scripts/black_dave_contact.c",
    "scripts/black_dave_block.c",
    "scripts/entity_enemy_contact.c",
    "scripts/entity_pose_overlay.c",
    "scripts/entity_tech_demo.c",
    "scripts/black_dave_pose_qa.c",
    "scripts/homeless_man_ai.c",
    "scripts/police_officer_ai.c",
    "scripts/police_officer_block.c",
    "scripts/update.c",
)
RUNTIME_GLOBS = (
    "chars/black_dave/sprites/*.png",
    "chars/black_dave/effects/*.png",
    "chars/homeless_man/sprites/*.png",
    "chars/police_officer/sprites/*.png",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(resolved)


def preflight(data_root: Path, pak_path: Path | None = None) -> None:
    command = [sys.executable, str(Path(__file__).with_name("Preflight-OpenBOR-Assets.py")), "--data", str(data_root)]
    if pak_path is not None:
        command.extend(["--pak", str(pak_path)])
    subprocess.run(command, check=True)


def copy_clean_payload(source_root: Path, staging_root: Path) -> None:
    """Copy only files reachable by the entity tech demo into a clean data root."""
    for relative in ROOT_FILES + RUNTIME_FILES:
        source = source_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"required package input is missing: {source}")
        target = staging_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for pattern in RUNTIME_GLOBS:
        matches = sorted(source_root.glob(pattern))
        if not matches:
            raise FileNotFoundError(f"required package inputs are missing: {source_root / pattern}")
        for source in matches:
            relative = source.relative_to(source_root)
            target = staging_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("openbor/data"))
    parser.add_argument("--output", type=Path, default=Path("openbor/releases/entity_tech_demo/TheFadesOfFate2_EntityTechDemo.pak"))
    parser.add_argument("--manifest", type=Path, default=Path("openbor/releases/entity_tech_demo/package_manifest.json"))
    parser.add_argument(
        "--runtime-exe",
        type=Path,
        required=True,
        help="exact pinned executable used for release/gameplay evidence",
    )
    args = parser.parse_args()
    data_root = args.data.resolve()
    runtime_exe = args.runtime_exe.resolve()
    if not runtime_exe.is_file():
        raise SystemExit(f"Pinned OpenBOR executable is missing: {runtime_exe}")
    preflight(data_root)
    with tempfile.TemporaryDirectory(prefix="fof2_entity_pak_") as temp:
        package_root = Path(temp) / "data"
        copy_clean_payload(data_root, package_root)
        preflight(package_root)
        files = sorted(
            (path for path in package_root.rglob("*") if path.is_file()),
            key=lambda p: p.relative_to(package_root).as_posix().lower(),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        records: list[tuple[int, int, bytes]] = []
        file_records: list[dict[str, object]] = []
        with args.output.open("wb") as pak:
            pak.write(b"PACK")
            pak.write(struct.pack("<I", 0))
            for path in files:
                relative = path.relative_to(package_root).as_posix()
                name = ("data\\" + relative.replace("/", "\\")).encode("ascii") + b"\0"
                offset = pak.tell()
                payload = path.read_bytes()
                pak.write(payload)
                records.append((offset, len(payload), name))
                file_records.append({"path": f"data/{relative}", "size": len(payload), "sha256": sha256(path)})
            table_offset = pak.tell()
            for offset, size, name in records:
                pak.write(struct.pack("<III", 12 + len(name), offset, size))
                pak.write(name)
            pak.write(struct.pack("<I", table_offset))
        preflight(package_root, args.output.resolve())
    manifest = {
        "schema_version": 2,
        "engine": "OpenBOR",
        "engine_build": 7949,
        "engine_reported_commit": "0ece95d",
        "runtime_executable": {
            "path": "OpenBOR.exe (not redistributed; supply pinned Build 7949 executable)",
            "size": runtime_exe.stat().st_size,
            "sha256": sha256(runtime_exe),
        },
        "pose_showcase_provenance": {
            "black_dave_schedule": {
                "path": "openbor/data/chars/black_dave/black_dave_pose_qa_schedule.json",
                "sha256": sha256(data_root / "chars/black_dave/black_dave_pose_qa_schedule.json"),
            },
            "harness_sha256": sha256(data_root / "scripts/entity_tech_demo.c"),
            "overlay_sha256": sha256(data_root / "scripts/entity_pose_overlay.c"),
            "pose_count": 460,
            "baseline_index": 4095,
        },
        "format": "PACK_v0_PAK32",
        "profile": "entity_tech_demo_dependency_closure",
        "release_gate_policy": {
            "visible_pose_proof": "temporarily_bypassed_by_owner_for_demo_release",
            "art_uniqueness_and_implementation_reachability": "required_and_passed",
        },
        "source_data": portable_path(data_root),
        "file_count": len(records),
        "files": file_records,
        "table_offset": table_offset,
        "output": portable_path(args.output),
        "sha256": sha256(args.output),
        "size": args.output.stat().st_size,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
