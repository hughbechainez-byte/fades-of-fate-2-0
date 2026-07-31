"""Generate a release-ready content manifest and packed asset bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_ASSET = "fades-of-fate-content-manifest.json"
PACK_ASSET = "fades-of-fate-content-pack.zip"


@dataclass(frozen=True)
class FileRecord:
    path: str
    sha256: str
    size: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131_072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_assets(root: Path) -> list[Path]:
    files: list[Path] = []
    for folder in ("assets", "data"):
        folder_root = root / folder
        if not folder_root.is_dir():
            continue
        for path in folder_root.rglob("*"):
            if path.is_file():
                files.append(path)
    return files


def _parse_game_version(project_root: Path) -> str:
    game_file = project_root / "src" / "game.py"
    with game_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("VERSION = "):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "unknown"


def _git_head(project_root: Path) -> str:
    try:
        process = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return process.stdout.strip()
    except Exception:
        return "unknown"


def _build_manifest(
    project_root: Path,
    revision: int,
    game_version: str,
    records: list[FileRecord],
    pack: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "content_version": game_version,
        "content_revision": revision,
        "minimum_game_version": game_version,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": _git_head(project_root),
        "pack": pack,
        "files": [record.__dict__ for record in records],
    }


def _build_pack(project_root: Path, output: Path, files: list[Path]) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            relative = file_path.relative_to(project_root)
            archive.write(file_path, arcname=str(relative))
            total_bytes += file_path.stat().st_size
    return total_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a content release manifest and pack")
    parser.add_argument("--project-root", default=".", help="project root directory")
    parser.add_argument("--output-dir", default="dist/content", help="output folder")
    parser.add_argument(
        "--content-revision",
        type=int,
        default=None,
        help="content pack revision",
    )
    parser.add_argument(
        "--content-version",
        default=None,
        help="content version label",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    output_dir = project_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    files = _walk_assets(project_root)
    records = [FileRecord(str(file.relative_to(project_root)), _sha256(file), file.stat().st_size) for file in files]
    pack_path = output_dir / PACK_ASSET
    _build_pack(project_root, pack_path, files)
    pack_hash = _sha256(pack_path)
    game_version = args.content_version or _parse_game_version(project_root)
    revision = int(args.content_revision or 1)

    pack_metadata = {
        "asset": PACK_ASSET,
        "sha256": pack_hash,
        "size": pack_path.stat().st_size,
    }
    manifest_payload = _build_manifest(
        project_root,
        revision=revision,
        game_version=game_version,
        records=records,
        pack=pack_metadata,
    )

    manifest_path = output_dir / MANIFEST_ASSET
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest_payload, handle, indent=2, sort_keys=True)

    print(json.dumps(
        {
            "content_manifest": str(manifest_path),
            "content_pack": str(pack_path),
            "content_revision": manifest_payload["content_revision"],
            "pack_bytes": manifest_payload["pack"]["size"],
            "files": len(records),
        },
        indent=2,
    ))
    print(f"WROTE_MANIFEST={manifest_path}")
    print(f"WROTE_PACK={pack_path}")


if __name__ == "__main__":
    main()
