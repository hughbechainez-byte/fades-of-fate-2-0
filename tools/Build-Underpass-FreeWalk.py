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


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def make_panels() -> None:
    background = STAGE_DATA / "levels/i8_underpass/background.png"
    panels = STAGE_DATA / "levels/i8_underpass/panels"
    panels.mkdir(parents=True, exist_ok=True)
    image = Image.open(background).convert("P")
    if image.size[1] != 360:
        raise ValueError(f"underpass background must be 360px high, got {image.size}")
    width = image.size[0]
    starts = [0, 640, max(0, width - 640)]
    names: list[str] = []
    for index, start in enumerate(starts, 1):
        panel = image.crop((start, 0, min(start + 640, width), 360))
        if panel.width < 640:
            padded = Image.new("P", (640, 360), 0)
            padded.putpalette(image.getpalette())
            padded.paste(panel, (0, 0))
            panel = padded
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
                "spawn1 200 280 0",
                "levelscript data/scripts/contract.c",
                *[f"panel data/levels/i8_underpass/panels/{name}" for name in names],
                "order abc",
                "at 0",
                "wait",
                "at 750",
                "",
            ]
        ),
        encoding="utf-8",
    )


def make_freewalk_model() -> None:
    runtime_data = ROOT / "openbor/runtime/data"
    shutil.copytree(runtime_data / "sprites/black_dave", STAGE_DATA / "sprites/black_dave", dirs_exist_ok=True)
    (STAGE_DATA / "models").mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime_data / "models/black_dave.txt", STAGE_DATA / "models/black_dave.txt")
    (STAGE_DATA / "models.txt").write_text(
        "# OpenBOR 4.0 compatibility model registry\n"
        "maxattacks 4\n"
        "maxfreespecials 3\n"
        "load BlackDave data/models/black_dave.txt\n",
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
