"""Build the manifest consumed by the Windows in-game application updater."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131_072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version(project_root: Path) -> str:
    game_file = project_root / "src" / "game.py"
    for line in game_file.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("VERSION = "):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("src/game.py does not declare FadesGame.VERSION")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--package-url", required=True)
    parser.add_argument("--output", default="dist/fades-of-fate-app-manifest.json")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    package = (project_root / args.package).resolve()
    if not package.is_file():
        raise FileNotFoundError(package)
    if not re.fullmatch(r"v.+", args.release_tag):
        raise ValueError("release tag must start with v")
    if not args.package_url.startswith("https://github.com/"):
        raise ValueError("package URL must be an HTTPS GitHub URL")

    version = _version(project_root)
    if version != args.release_tag[1:]:
        raise ValueError(
            f"FadesGame.VERSION {version!r} must match release tag {args.release_tag!r}"
        )

    payload: dict[str, Any] = {
        "schema_version": 1,
        "product": "The Fades of Fate",
        "platform": "windows-x64",
        "version": version,
        "release_tag": args.release_tag,
        "package_asset_name": package.name,
        "package_url": args.package_url,
        "package_sha256": _sha256(package),
        "package_size": package.stat().st_size,
    }
    output = (project_root / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"WROTE_APP_UPDATE_MANIFEST={output}")


if __name__ == "__main__":
    main()
