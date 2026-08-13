"""Build a native OpenBOR PACK v0 from the tracked 2.0 data tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preflight(data_root: Path, pak_path: Path | None = None) -> None:
    command = [sys.executable, str(Path(__file__).with_name("Preflight-OpenBOR-Assets.py")), "--data", str(data_root)]
    if pak_path is not None:
        command.extend(["--pak", str(pak_path)])
    subprocess.run(command, check=True)


def git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


def packaged_entry_count(pak_path: Path) -> int:
    size = pak_path.stat().st_size
    if size < 12:
        raise SystemExit(f"Invalid PACK file (too small): {pak_path}")
    with pak_path.open("rb") as pak:
        if pak.read(4) != b"PACK":
            raise SystemExit(f"Invalid PACK file signature: {pak_path}")
        pak.seek(-4, 2)
        table_offset = struct.unpack("<I", pak.read(4))[0]
        table_end = size - 4
        if table_offset < 8 or table_offset > table_end:
            raise SystemExit(f"Invalid PACK table offset: {table_offset}")
        count = 0
        cursor = table_offset
        while cursor < table_end:
            pak.seek(cursor)
            header = pak.read(12)
            if len(header) != 12:
                raise SystemExit(f"Truncated PACK entry table at byte {cursor}")
            record_size, payload_offset, payload_size = struct.unpack("<III", header)
            if record_size < 13 or cursor + record_size > table_end:
                raise SystemExit(f"Invalid PACK entry record at byte {cursor}")
            name = pak.read(record_size - 12)
            if not name.endswith(b"\0") or payload_offset + payload_size > table_offset:
                raise SystemExit(f"Invalid PACK entry payload at byte {cursor}")
            count += 1
            cursor += record_size
        return count


def stage_manifest_asset_set(data_root: Path) -> dict[str, str] | None:
    candidates = sorted(
        data_root.rglob("*manifest.json"),
        key=lambda path: path.relative_to(data_root).as_posix().lower(),
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        asset_set_sha256 = payload.get("asset_set_sha256") if isinstance(payload, dict) else None
        if isinstance(asset_set_sha256, str) and asset_set_sha256:
            return {
                "path": "data/" + path.relative_to(data_root).as_posix(),
                "asset_set_sha256": asset_set_sha256,
            }
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("openbor/data"))
    parser.add_argument("--output", type=Path, default=Path("build/openbor_black_dave/TheFadesOfFate2.pak"))
    parser.add_argument("--manifest", type=Path, default=Path("build/openbor_black_dave/package_manifest.json"))
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    data_root = args.data.resolve()
    preflight(data_root)
    files = sorted((path for path in data_root.rglob("*") if path.is_file()), key=lambda p: p.relative_to(data_root).as_posix().lower())
    if not files:
        raise SystemExit(f"No tracked module data found under {data_root}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records: list[tuple[int, int, bytes]] = []
    source_files_sha256: dict[str, str] = {}
    with args.output.open("wb") as pak:
        pak.write(b"PACK")
        pak.write(struct.pack("<I", 0))
        for path in files:
            relative_path = path.relative_to(data_root).as_posix()
            name = ("data\\" + relative_path.replace("/", "\\")).encode("ascii") + b"\0"
            offset = pak.tell()
            payload = path.read_bytes()
            pak.write(payload)
            records.append((offset, len(payload), name))
            source_files_sha256["data/" + relative_path] = hashlib.sha256(payload).hexdigest()
        table_offset = pak.tell()
        for offset, size, name in records:
            pak.write(struct.pack("<III", 12 + len(name), offset, size))
            pak.write(name)
        pak.write(struct.pack("<I", table_offset))
    actual_entry_count = packaged_entry_count(args.output)
    entry_counts_match = actual_entry_count == len(records)
    if not entry_counts_match:
        raise SystemExit(
            f"PACK entry count mismatch: expected {len(records)}, found {actual_entry_count}"
        )
    runtime_path = repo_root / "openbor" / "runtime" / "OpenBOR.exe"
    manifest = {
        "schema_version": 1,
        "engine": "OpenBOR",
        "format": "PACK_v0_PAK32",
        "source_commit": git_commit(repo_root),
        "source_data": str(data_root),
        "source_files_sha256": source_files_sha256,
        "file_count": len(records),
        "packaged_entry_count_verification": {
            "expected": len(records),
            "actual": actual_entry_count,
            "matches": entry_counts_match,
        },
        "table_offset": table_offset,
        "runtime": {
            "path": str(runtime_path.resolve()),
            "build_label": "OpenBOR 4.0 Build 7949",
            "openbor_exe_sha256": sha256(runtime_path) if runtime_path.is_file() else None,
        },
        "output": str(args.output.resolve()),
        "sha256": sha256(args.output),
        "size": args.output.stat().st_size,
    }
    stage_manifest = stage_manifest_asset_set(data_root)
    if stage_manifest is not None:
        manifest["stage_manifest"] = stage_manifest
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
    args.manifest.write_text(manifest_json + "\n", encoding="utf-8")
    preflight(data_root, args.output.resolve())
    print(
        json.dumps(
            {
                "file_count": manifest["file_count"],
                "output": manifest["output"],
                "sha256": manifest["sha256"],
                "size": manifest["size"],
                "stage_asset_set_sha256": (manifest.get("stage_manifest") or {}).get("asset_set_sha256"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
