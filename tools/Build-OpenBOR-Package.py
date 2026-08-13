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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("openbor/data"))
    parser.add_argument("--output", type=Path, default=Path("build/openbor_black_dave/TheFadesOfFate2.pak"))
    parser.add_argument("--manifest", type=Path, default=Path("build/openbor_black_dave/package_manifest.json"))
    args = parser.parse_args()
    data_root = args.data.resolve()
    preflight(data_root)
    files = sorted((path for path in data_root.rglob("*") if path.is_file()), key=lambda p: p.relative_to(data_root).as_posix().lower())
    if not files:
        raise SystemExit(f"No tracked module data found under {data_root}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records: list[tuple[int, int, bytes]] = []
    with args.output.open("wb") as pak:
        pak.write(b"PACK")
        pak.write(struct.pack("<I", 0))
        for path in files:
            name = ("data\\" + path.relative_to(data_root).as_posix().replace("/", "\\")).encode("ascii") + b"\0"
            offset = pak.tell()
            payload = path.read_bytes()
            pak.write(payload)
            records.append((offset, len(payload), name))
        table_offset = pak.tell()
        for offset, size, name in records:
            pak.write(struct.pack("<III", 12 + len(name), offset, size))
            pak.write(name)
        pak.write(struct.pack("<I", table_offset))
    manifest = {
        "schema_version": 1,
        "engine": "OpenBOR",
        "format": "PACK_v0_PAK32",
        "source_data": str(data_root),
        "file_count": len(records),
        "table_offset": table_offset,
        "output": str(args.output.resolve()),
        "sha256": sha256(args.output),
        "size": args.output.stat().st_size,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    preflight(data_root, args.output.resolve())
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
