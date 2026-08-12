"""Create a clean underpass review sheet from the OpenBOR frame package."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "openbor/data/chars/black_dave"
PLATE = ROOT / "content/setpieces/underpass_i8/lookdev/target_renders/ch1_l2_i8_underpass_target_clean.png"
OUT = ROOT / "build/openbor_black_dave_review"


def main() -> None:
    manifest = json.loads((MODEL / "black_dave_openbor_manifest.json").read_text(encoding="utf-8"))
    picks = [("idle", 0), ("walk", 2), ("black_dave_v2_regular_01", 2), ("black_dave_v2_kick_01", 3), ("black_dave_v2_power_01", 2), ("hurt", 2), ("down", 3), ("recovery", 4)]
    plate = Image.open(PLATE).convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
    sheet = Image.new("RGB", (1280, 720 * len(picks)), (9, 13, 22))
    font = ImageFont.load_default()
    for row, (clip, index) in enumerate(picks):
        frame_rel = manifest["clips"][clip]["frames"][index]
        frame = Image.open(MODEL / frame_rel).convert("RGBA")
        frame = frame.resize((frame.width * 3, frame.height * 3), Image.Resampling.NEAREST)
        scene = plate.copy().convert("RGBA")
        shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow)
        draw.ellipse((500, 590, 790, 632), fill=(4, 9, 18, 124))
        scene.alpha_composite(shadow)
        scene.alpha_composite(frame, (440, 246))
        scene = scene.convert("RGB")
        ImageDraw.Draw(scene).text((24, 18), f"OPENBOR BLACK DAVE / {clip} / frame {index + 1} of 5", fill=(235, 240, 246), font=font)
        sheet.paste(scene, (0, row * 720))
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT / "black_dave_underpass_openbor_pose_review.png", optimize=False)
    print(OUT / "black_dave_underpass_openbor_pose_review.png")


if __name__ == "__main__":
    main()
