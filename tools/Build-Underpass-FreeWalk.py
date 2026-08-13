"""Build the authored layered underpass tech-demo package without rewriting it."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
STAGE_DATA = ROOT / "build/underpass_techdemo_data"
PACKAGE_DIR = ROOT / "build/underpass_techdemo"
SOURCE_DATA = ROOT / "openbor/data"
PANEL_ROOT = SOURCE_DATA / "levels/i8_underpass/panels"


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def validate_authored_stage() -> None:
    """Reject the former overlapping-crop fallback and require authored A-D panels."""
    hashes: set[bytes] = set()
    for name in "abcd":
        path = PANEL_ROOT / f"underpass_{name}.png"
        if not path.is_file():
            raise FileNotFoundError(f"Missing authored underpass panel: {path}")
        with Image.open(path) as image:
            if image.size != (640, 360) or image.mode != "P" or image.info.get("transparency") != 0:
                raise ValueError(f"{path}: expected indexed transparent 640x360 authored panel")
            payload = image.tobytes()
        if payload in hashes:
            raise ValueError(f"{path}: duplicate panel pixels are forbidden")
        hashes.add(payload)


def main() -> int:
    run("tools/Build-Underpass-Stage.py")
    validate_authored_stage()
    run("tools/Preflight-OpenBOR-Assets.py", "--data", str(SOURCE_DATA))

    if STAGE_DATA.exists():
        shutil.rmtree(STAGE_DATA)
    shutil.copytree(SOURCE_DATA, STAGE_DATA)

    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    run(
        "tools/Build-OpenBOR-Package.py",
        "--data",
        str(STAGE_DATA),
        "--output",
        str(PACKAGE_DIR / "UnderpassTechDemo.pak"),
        "--manifest",
        str(PACKAGE_DIR / "package_manifest.json"),
    )
    print(PACKAGE_DIR / "UnderpassTechDemo.pak")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
