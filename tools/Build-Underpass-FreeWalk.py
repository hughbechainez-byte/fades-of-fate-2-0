"""Build the OpenBOR-compatible panel-based underpass free-walk package."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
STAGE_DATA = ROOT / "build/underpass_freewalk_data"
PACKAGE_DIR = ROOT / "build/underpass_freewalk"
SOURCE_DATA = ROOT / "openbor/data"
MASTER_ART = ROOT / "content/setpieces/underpass_i8/art/black_dave_demo_master.png"


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def make_panels() -> None:
    panels = STAGE_DATA / "levels/i8_underpass/panels"
    panels.mkdir(parents=True, exist_ok=True)
    source = Image.open(MASTER_ART).convert("RGB")
    # A single master palette keeps every panel deterministic in Build 7949.
    palette = source.quantize(colors=255, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    crops = ((0.00, 0.74), (0.13, 0.87), (0.26, 1.00))
    names: list[str] = []
    for index, (left_ratio, right_ratio) in enumerate(crops, 1):
        left = round(source.width * left_ratio)
        right = round(source.width * right_ratio)
        view = source.crop((left, 0, right, source.height)).resize((640, 360), Image.Resampling.LANCZOS)
        panel = view.quantize(palette=palette, dither=Image.Dither.NONE)
        panel.info["transparency"] = 0
        name = f"underpass_{index:02d}.png"
        panel.save(panels / name, optimize=False)
        names.append(name)
    level = STAGE_DATA / "levels/i8_underpass.txt"
    level.write_text(
        "\n".join(
            [
                "settime 0",
                "notime 1",
                "noslow 1",
                "direction both",
                "spawn1 220 280 0",
                "levelscript data/scripts/contract.c",
                *[f"panel data/levels/i8_underpass/panels/{name}" for name in names],
                "order abc",
                "cameratype 0",
                "at 0",
                "wait",
                "at 1500",
                "",
            ]
        ),
        encoding="utf-8",
    )


def make_freewalk_model() -> None:
    legacy_black_dave = STAGE_DATA / "chars" / "blackdave"
    if legacy_black_dave.exists():
        shutil.rmtree(legacy_black_dave)
    (STAGE_DATA / "models.txt").write_text(
        "# OpenBOR 4.0 compatibility model registry\n"
        "maxattacks 4\n"
        "maxfreespecials 7\n"
        "load BlackDave data/chars/black_dave/black_dave.txt\n",
        encoding="utf-8",
    )


def main() -> int:
    run("tools/Build-OpenBOR-Black-Dave.py")
    if STAGE_DATA.exists():
        shutil.rmtree(STAGE_DATA)
    shutil.copytree(SOURCE_DATA, STAGE_DATA)
    make_freewalk_model()
    make_panels()
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    run(
        "tools/Build-OpenBOR-Package.py",
        "--data",
        str(STAGE_DATA),
        "--output",
        str(PACKAGE_DIR / "UnderpassFreeWalk.pak"),
        "--manifest",
        str(PACKAGE_DIR / "package_manifest.json"),
    )
    print(PACKAGE_DIR / "UnderpassFreeWalk.pak")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
