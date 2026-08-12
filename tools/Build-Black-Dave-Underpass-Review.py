"""Build a target-render style calibration review from the graded Dave atlas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "assets/sprites/black_dave_full_library_v1.png"
METADATA = ROOT / "assets/sprites/black_dave_full_library_v1.json"


def load_font(size: int):
    try:
        return ImageFont.truetype("segoeui.ttf", size)
    except OSError:
        return ImageFont.load_default()


def dave_cell(clip_id: str, pose_index: int) -> Image.Image:
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    clip = metadata["clips"][clip_id]
    atlas = Image.open(ATLAS).convert("RGBA")
    return atlas.crop((pose_index * 224, int(clip["row"]) * 160, (pose_index + 1) * 224, (int(clip["row"]) + 1) * 160))


def composite(plate: Image.Image, *, output_size: tuple[int, int]) -> Image.Image:
    plate = plate.convert("RGB").resize(output_size, Image.Resampling.LANCZOS).convert("RGBA")
    # Keep the sprite nearest-neighbor and apply only a soft scene contact shadow.
    body = dave_cell("black_dave_v2_regular_04", 2)
    body = body.resize((body.width * 3, body.height * 3), Image.Resampling.NEAREST)
    body_layer = Image.new("RGBA", plate.size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", plate.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.ellipse((438, 596, 712, 632), fill=(4, 10, 20, 112))
    body_layer.alpha_composite(body, (380, 276))
    plate = Image.alpha_composite(plate, shadow)
    return Image.alpha_composite(plate, body_layer).convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--clean-plate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = Image.open(args.original).convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
    graded = composite(Image.open(args.clean_plate), output_size=(1280, 720))
    review = Image.new("RGB", (2560, 760), (12, 16, 25))
    review.paste(original, (0, 40))
    review.paste(graded, (1280, 40))
    draw = ImageDraw.Draw(review)
    font = load_font(22)
    draw.text((24, 10), "TARGET RENDER / CURRENT DAVE", fill=(230, 235, 242), font=font)
    draw.text((1304, 10), "UNDERPASS GRADE / SMALLER ROOTED DAVE", fill=(230, 235, 242), font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    review.save(args.output, optimize=False)
    single = args.output.with_name(args.output.stem + "_after.png")
    graded.save(single, optimize=False)
    print(args.output)
    print(single)


if __name__ == "__main__":
    main()
