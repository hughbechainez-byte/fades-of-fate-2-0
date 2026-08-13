"""Author the layered sunset-underpass stage assets for OpenBOR Build 7949."""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "content/setpieces/underpass_i8/art_source/sunset_techdemo"
REVIEW_ROOT = ROOT / "content/setpieces/underpass_i8/review/sunset_techdemo"
RUNTIME_ROOT = ROOT / "openbor/data/levels/i8_underpass"
PANEL_ROOT = RUNTIME_ROOT / "panels"
ART_ROOT = RUNTIME_ROOT / "art"
SCENERY_ROOT = RUNTIME_ROOT / "scenery"
FOLIAGE_MODEL_PATH = RUNTIME_ROOT / "underpass_foliage.txt"
MANIFEST_PATH = RUNTIME_ROOT / "underpass_manifest.json"

VIEWPORT = (640, 360)
PANEL_NAMES = ("a", "b", "c", "d")
WORLD_WIDTH = VIEWPORT[0] * len(PANEL_NAMES)
STAGE_SEED = 0xFAD320
FOLIAGE_ROOTS = (145, 535, 825, 1180, 1505, 1830, 2175, 2410)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def resize_sources() -> list[Image.Image]:
    panels: list[Image.Image] = []
    for name in PANEL_NAMES:
        path = SOURCE_ROOT / f"panel_{name}_source.png"
        if not path.is_file():
            raise FileNotFoundError(f"Missing authored stage source: {path}")
        with Image.open(path) as source:
            panels.append(ImageOps.fit(source.convert("RGB"), VIEWPORT, Image.Resampling.LANCZOS))
    return panels


def bridge_seams(panels: list[Image.Image], radius: int = 28) -> Image.Image:
    """Fade each edge into one shared shadow column without ghosting landmarks."""
    panorama = Image.new("RGB", (WORLD_WIDTH, VIEWPORT[1]))
    for index, panel in enumerate(panels):
        panorama.paste(panel, (index * VIEWPORT[0], 0))
    source = panorama.copy()
    source_pixels, target_pixels = source.load(), panorama.load()
    for seam in range(VIEWPORT[0], WORLD_WIDTH, VIEWPORT[0]):
        for y in range(VIEWPORT[1]):
            edge = [source_pixels[x, y] for x in range(seam - 4, seam + 4)]
            average = tuple(sum(pixel[channel] for pixel in edge) // len(edge) for channel in range(3))
            shadow = tuple(max(4, round(channel * 0.72)) for channel in average)
            for offset in range(-radius, 0):
                x = seam + offset
                t = round(((offset + radius + 1) / radius) * 4) / 4
                original = source_pixels[x, y]
                target_pixels[x, y] = tuple(round(a * (1.0 - t) + b * t) for a, b in zip(original, shadow))
            for offset in range(0, radius):
                x = seam + offset
                t = round(((offset + 1) / radius) * 4) / 4
                original = source_pixels[x, y]
                target_pixels[x, y] = tuple(round(a * (1.0 - t) + b * t) for a, b in zip(shadow, original))
    return panorama


def panel_alpha_mask() -> Image.Image:
    """Cut authored sky portals while keeping all floor, fence, and structure world-locked."""
    mask = Image.new("L", (WORLD_WIDTH, VIEWPORT[1]), 255)
    draw = ImageDraw.Draw(mask)

    # A: broad sunset mouth, excluding its offset pier.
    draw.polygon([(124, 76), (632, 76), (632, 172), (184, 172)], fill=0)
    draw.rectangle((444, 70, 536, 190), fill=255)

    # B: narrow warm slit between the staggered piers.
    b = 640
    draw.polygon([(b + 208, 118), (b + 376, 118), (b + 376, 172), (b + 208, 172)], fill=0)

    # C: the small release cue at the right edge of the shadow core.
    c = 1280
    draw.polygon([(c + 568, 78), (c + 632, 78), (c + 632, 172), (c + 568, 172)], fill=0)

    # D: expanding exit portal, excluding the final pier.
    d = 1920
    draw.polygon([(d + 108, 136), (d + 420, 38), (d + 632, 0), (d + 632, 172), (d + 108, 172)], fill=0)
    draw.rectangle((d + 324, 54, d + 416, 192), fill=255)
    return mask


def coarse_canvas(size: tuple[int, int], scale: int = 4, color=(0, 0, 0, 0)) -> Image.Image:
    return Image.new("RGBA", (math.ceil(size[0] / scale), math.ceil(size[1] / scale)), color)


def upscale(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return image.resize(size, Image.Resampling.NEAREST)


def make_background() -> Image.Image:
    image = Image.new("RGB", VIEWPORT)
    draw = ImageDraw.Draw(image)
    bands = [
        (0, 58, "#4a294d"),
        (58, 98, "#8b3e62"),
        (98, 132, "#d85b62"),
        (132, 170, "#ee7c58"),
        (170, 216, "#b85160"),
        (216, 360, "#161a25"),
    ]
    for top, bottom, color in bands:
        draw.rectangle((0, top, VIEWPORT[0], bottom - 1), fill=color)
    return image


def saturated_portal(source: Image.Image, box: tuple[int, int, int, int], size: tuple[int, int]) -> Image.Image:
    crop = ImageOps.fit(source.crop(box), size, Image.Resampling.LANCZOS)
    saturation = crop.convert("HSV").getchannel("S")
    value = crop.convert("HSV").getchannel("V")
    mask = Image.new("L", crop.size)
    mask.putdata(bytes(255 if sat >= 34 and val >= 34 else 0 for sat, val in zip(saturation.tobytes(), value.tobytes())))
    rgba = crop.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def make_far(sources: list[Image.Image]) -> Image.Image:
    size = (2048, 360)
    image = coarse_canvas(size)
    draw = ImageDraw.Draw(image)
    width, height = image.size
    sky = ["#38213f", "#63304f", "#9a405b", "#d8595e", "#eb7658", "#f18a5a"]
    for y in range(height):
        draw.line((0, y, width, y), fill=sky[min(len(sky) - 1, y * len(sky) // 55)])

    rng = random.Random(STAGE_SEED)
    # Two original low-contrast ridge lines.
    for ridge, color, base in ((0, "#633352", 50), (1, "#422c47", 58)):
        points = [(0, height)]
        x = 0
        while x <= width:
            peak = base - rng.randint(2, 15) - (5 if (x // 70 + ridge) % 3 == 0 else 0)
            points.append((x, peak))
            x += rng.randint(34, 58)
        points.extend([(width, height), (0, height)])
        draw.polygon(points, fill=color)

    # Sparse city glints, kept below the fighter readability band.
    for x in range(12, width - 8, 29):
        if rng.random() < 0.55:
            y = rng.randint(57, 65)
            draw.rectangle((x, y, x + rng.randint(0, 1), y + 1), fill=rng.choice(("#bd5663", "#d86b62", "#8d4761")))
    far = upscale(image, size).convert("RGBA")
    # Preserve the concept's authored clouds and mountain color while removing
    # low-saturation concrete, fence, and floor pixels from the far plane.
    far.alpha_composite(saturated_portal(sources[0], (120, 72, 640, 202), (1024, 208)), (0, 0))
    far.alpha_composite(saturated_portal(sources[3], (104, 22, 640, 210), (1024, 208)), (1024, 0))
    return far.convert("RGB")


def draw_palm(draw: ImageDraw.ImageDraw, x: int, ground: int, height: int, color: str) -> None:
    crown = ground - height
    draw.line((x, ground, x, crown + 3), fill=color, width=1)
    for dx, dy in ((-5, 1), (-4, -2), (5, 1), (4, -2), (-2, -4), (2, -4)):
        draw.line((x, crown, x + dx, crown + dy), fill=color, width=1)


def make_mid() -> Image.Image:
    size = (1792, 360)
    image = coarse_canvas(size, scale=2)
    draw = ImageDraw.Draw(image)
    width, height = image.size
    rng = random.Random(STAGE_SEED + 1)
    shrub = "#24283a"
    points = [(0, height)]
    for x in range(0, width + 1, 12):
        points.append((x, 104 - rng.randint(0, 12)))
    points.extend([(width, height), (0, height)])
    draw.polygon(points, fill=shrub)
    for x in (80, 182, 312, 468, 630, 794):
        draw_palm(draw, x, 116, rng.randint(34, 56), "#29243a")
    for x in range(36, width, 94):
        if rng.random() < 0.7:
            draw.point((x, rng.randint(106, 118)), fill=rng.choice(("#ba4e65", "#d56361", "#79405b")))
    return upscale(image, size)


def make_haze() -> Image.Image:
    size = (2816, 360)
    image = coarse_canvas(size)
    draw = ImageDraw.Draw(image)
    rng = random.Random(STAGE_SEED + 2)
    width, _ = image.size
    for band_y, color in ((48, "#6a405e"), (57, "#45516a"), (65, "#3b455b")):
        x = rng.randint(0, 20)
        while x < width:
            length = rng.randint(7, 24)
            if rng.random() < 0.62:
                draw.line((x, band_y + rng.randint(-2, 2), x + length, band_y + rng.randint(-2, 2)), fill=color)
            x += length + rng.randint(18, 42)
    for _ in range(90):
        x = rng.randrange(width)
        y = rng.randint(44, 75)
        draw.point((x, y), fill=rng.choice(("#8b5066", "#5a4863", "#344155")))
    return upscale(image, size)


def make_static_details() -> Image.Image:
    """Pixel-scale storytelling baked into the world plane, never screen-detached."""
    image = Image.new("RGBA", (WORLD_WIDTH, VIEWPORT[1]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rng = random.Random(STAGE_SEED + 3)

    # Torn paper and simple glyphs belong to concrete piers/walls, not the sky.
    posters = (
        (54, 126, "#755368", "#a46768"),
        (386, 190, "#536875", "#9b626a"),
        (716, 132, "#66566d", "#a76a60"),
        (1048, 116, "#4e6572", "#93616f"),
        (1490, 126, "#705267", "#b06b5c"),
        (1808, 116, "#526774", "#95616c"),
        (2076, 132, "#70546a", "#ad6a5d"),
        (2350, 190, "#526673", "#9d6268"),
    )
    for index, (x, y, paper, ink) in enumerate(posters):
        draw.rectangle((x, y, x + 11, y + 14), fill="#20232d")
        draw.rectangle((x + 1, y + 1, x + 10, y + 12), fill=paper)
        if index % 3 == 0:  # sunset disk glyph
            draw.rectangle((x + 3, y + 4, x + 7, y + 6), fill=ink)
            draw.line((x + 2, y + 8, x + 8, y + 8), fill="#343746")
        elif index % 3 == 1:  # angular bird / chevron glyph
            draw.line((x + 2, y + 8, x + 5, y + 5, x + 8, y + 8), fill=ink, width=1)
        else:  # tiny cassette/window glyph
            draw.rectangle((x + 2, y + 4, x + 8, y + 9), outline=ink)
            draw.point((x + 4, y + 7), fill="#282d38")
            draw.point((x + 7, y + 7), fill="#282d38")
        draw.rectangle((x + 8, y + 11, x + 10, y + 14), fill=(0, 0, 0, 0))

    # Low-contrast pixel graffiti and utility marks add authored detail behind Dave.
    for x, y, color in ((78, 162, "#7b506a"), (870, 154, "#5f6877"), (1378, 146, "#765069"), (2240, 158, "#875466")):
        draw.line((x, y, x + 5, y - 4, x + 10, y, x + 15, y - 5), fill=color, width=2)
        draw.point((x + 4, y + 3), fill=color)
        draw.point((x + 12, y + 2), fill=color)
    for x in (244, 612, 972, 1248, 1652, 2018, 2460):
        draw.rectangle((x, 215, x + 12, 217), fill="#343b46")
        draw.rectangle((x + 2, 218, x + 9, 219), fill="#6d4d5e")

    # Root shadows and static dead leaves visually pin the animated curb weeds.
    for root_x in FOLIAGE_ROOTS:
        draw.rectangle((root_x - 17, 246, root_x + 17, 248), fill="#151b20")
        draw.rectangle((root_x - 9, 244, root_x + 10, 246), fill="#272d2b")
        for _ in range(5):
            leaf_x = root_x + rng.randint(-22, 22)
            leaf_y = rng.randint(248, 254)
            draw.rectangle((leaf_x, leaf_y, leaf_x + rng.randint(1, 3), leaf_y + 1), fill=rng.choice(("#57483b", "#66503f", "#3d4238")))

    # Walkable asphalt gets readable, non-colliding pixel props and surface marks.
    cracks = (
        (92, 290), (286, 318), (492, 274), (708, 334), (914, 294),
        (1122, 322), (1328, 282), (1542, 336), (1740, 302), (1950, 326),
        (2188, 284), (2380, 318),
    )
    for index, (x, y) in enumerate(cracks):
        color = "#303440" if index % 2 else "#242934"
        draw.line((x, y, x + 7, y - 3, x + 13, y + 1, x + 22, y - 5), fill=color, width=1)
        draw.line((x + 12, y, x + 15, y + 6), fill=color, width=1)
        draw.point((x + 24, y - 4), fill="#50505a")
    for x, y, color in (
        (180, 307, "#7c6870"), (560, 326, "#8c685d"), (788, 286, "#506d78"),
        (1018, 341, "#75606e"), (1250, 306, "#9a665a"), (1452, 278, "#536d78"),
        (1668, 327, "#77606b"), (1880, 292, "#9b6657"), (2112, 338, "#516c76"),
        (2295, 301, "#80616a"), (2490, 326, "#9a695b"),
    ):
        # Torn flyer / wrapper with a one-pixel cast shadow.
        draw.polygon([(x + 1, y + 2), (x + 9, y), (x + 13, y + 4), (x + 4, y + 6)], fill="#171c24")
        draw.polygon([(x, y), (x + 8, y - 2), (x + 12, y + 2), (x + 3, y + 4)], fill=color)
        draw.line((x + 3, y + 1, x + 8, y), fill="#b07a69")
    for x, y in ((354, 344), (1186, 268), (1606, 294), (2328, 348)):
        # Crushed can/bottle glints remain small enough not to compete with combat.
        draw.rectangle((x + 1, y + 2, x + 8, y + 4), fill="#171c23")
        draw.rectangle((x, y, x + 6, y + 2), fill="#566e78")
        draw.point((x + 1, y), fill="#a06a60")
        draw.point((x + 5, y + 2), fill="#8b7a73")

    # Asphalt aggregate breaks broad empty bands without becoming visual noise.
    for _ in range(150):
        x = rng.randrange(20, WORLD_WIDTH - 20)
        y = rng.randrange(258, 351)
        if min(abs(x - seam) for seam in (640, 1280, 1920)) < 30:
            continue
        color = rng.choice(("#252a34", "#303540", "#3c3c47", "#4a4149"))
        draw.point((x, y), fill=color)
        if rng.random() < 0.22:
            draw.point((x + 1, y), fill=color)
    return image


def make_foliage_frames() -> list[Image.Image]:
    """Three rooted pixel drawings; no full-screen sine/water distortion."""
    frames: list[Image.Image] = []
    for lean in (-2, 0, 2):
        image = Image.new("RGBA", (48, 40), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((15, 35, 33, 36), fill="#2b312c")
        stems = ((12, 11, -2), (18, 17, 1), (24, 22, -1), (30, 15, 2), (36, 10, 0))
        for index, (x, height, bias) in enumerate(stems):
            tip_x = x + lean + bias
            tip_y = 35 - height
            color = ("#3c4638", "#55513b", "#6a5740", "#485044", "#765c43")[index]
            draw.line((x, 35, x + bias // 2, 28, tip_x, tip_y), fill=color, width=2)
            draw.line((x + bias // 2, 28, x - 3 + lean, 25), fill=color, width=1)
            if index in (1, 3):
                draw.rectangle((tip_x - 1, tip_y, tip_x + 1, tip_y + 1), fill="#875f45")
        draw.point((10, 34), fill="#6b4f3c")
        draw.rectangle((37, 34, 40, 35), fill="#4e4438")
        frames.append(image)
    return frames


def foliage_model_text() -> str:
    frames = [f"data/levels/i8_underpass/scenery/foliage_sway_{index:02d}.png" for index in range(1, 4)]
    return "\n".join((
        "# Rooted, non-interactive stage foliage for the I-8 underpass.",
        "name UnderpassFoliage",
        "type none",
        "health 1",
        "shadow 0",
        "nomove 1",
        "subject_to_gravity 0",
        "offscreenkill 4096",
        "",
        "anim idle",
        "loop 1",
        "delay 42",
        "offset 24 36",
        f"frame {frames[0]}",
        f"frame {frames[1]}",
        f"frame {frames[2]}",
        f"frame {frames[1]}",
        "",
    ))


def make_palette(images: list[Image.Image]) -> tuple[Image.Image, list[int]]:
    samples = [image.convert("RGB").resize((min(image.width, 640), 90), Image.Resampling.BOX) for image in images]
    montage = Image.new("RGB", (max(image.width for image in samples), 90 * len(samples)))
    for index, image in enumerate(samples):
        montage.paste(image, (0, index * 90))
    quantized = montage.quantize(colors=255, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    colors = list((quantized.getpalette() or [])[: 255 * 3])
    colors.extend([0] * (255 * 3 - len(colors)))
    palette_image = Image.new("P", (1, 1))
    palette_image.putpalette(colors + colors[-3:])
    runtime_palette = [0, 255, 0] + colors
    return palette_image, runtime_palette[:768]


def indexed(image: Image.Image, palette_image: Image.Image, runtime_palette: list[int], alpha: Image.Image | None = None) -> Image.Image:
    rgba = image.convert("RGBA")
    indices = rgba.convert("RGB").quantize(palette=palette_image, dither=Image.Dither.NONE)
    source_data = indices.tobytes()
    alpha_data = (alpha or rgba.getchannel("A")).tobytes()
    output = Image.new("P", rgba.size, 0)
    output.putpalette(runtime_palette)
    output.putdata(bytes(0 if a == 0 else min(255, value + 1) for value, a in zip(source_data, alpha_data)))
    output.info["transparency"] = 0
    return output


def five_value_study(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    return gray.point(lambda value: min(255, (value // 52) * 64)).convert("P")


def build() -> dict:
    PANEL_ROOT.mkdir(parents=True, exist_ok=True)
    ART_ROOT.mkdir(parents=True, exist_ok=True)
    SCENERY_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)

    sources = resize_sources()
    panorama = bridge_seams(sources)
    static_details = make_static_details()
    detailed_panorama = panorama.convert("RGBA")
    detailed_panorama.alpha_composite(static_details)
    panorama = detailed_panorama.convert("RGB")
    alpha = panel_alpha_mask()
    background = make_background()
    far = make_far(sources)
    mid = make_mid()
    haze = make_haze()
    foliage_frames = make_foliage_frames()
    palette_image, runtime_palette = make_palette([panorama, background, far, mid, haze, *foliage_frames])

    indexed_background = indexed(background, palette_image, runtime_palette)
    indexed_background.save(RUNTIME_ROOT / "background.png", optimize=False)
    layer_images = {"far.png": far, "mid.png": mid, "haze.png": haze}
    for name, image in layer_images.items():
        indexed(image, palette_image, runtime_palette).save(ART_ROOT / name, optimize=False)
    stale_full_width_foliage = ART_ROOT / "foliage.png"
    if stale_full_width_foliage.is_file():
        stale_full_width_foliage.unlink()
    foliage_paths: list[Path] = []
    for frame_index, frame in enumerate(foliage_frames, 1):
        path = SCENERY_ROOT / f"foliage_sway_{frame_index:02d}.png"
        indexed(frame, palette_image, runtime_palette).save(path, optimize=False)
        foliage_paths.append(path)
    FOLIAGE_MODEL_PATH.write_text(foliage_model_text(), encoding="utf-8")

    runtime_panorama = Image.new("RGBA", (WORLD_WIDTH, VIEWPORT[1]), (0, 0, 0, 0))
    runtime_panorama.paste(panorama.convert("RGBA"), (0, 0), alpha)
    for index, name in enumerate(PANEL_NAMES):
        crop_box = (index * 640, 0, (index + 1) * 640, 360)
        panel = indexed(
            panorama.crop(crop_box),
            palette_image,
            runtime_palette,
            alpha.crop(crop_box),
        )
        panel.save(PANEL_ROOT / f"underpass_{name}.png", optimize=False)

    preview = far.resize((WORLD_WIDTH, 360), Image.Resampling.NEAREST).convert("RGBA")
    preview.alpha_composite(mid.resize((WORLD_WIDTH, 360), Image.Resampling.NEAREST))
    preview.alpha_composite(runtime_panorama)
    preview.alpha_composite(haze.resize((WORLD_WIDTH, 360), Image.Resampling.NEAREST))
    preview_foliage = foliage_frames[1]
    for root_x in FOLIAGE_ROOTS:
        preview.alpha_composite(preview_foliage, (root_x - 24, 248 - 36))
    preview.convert("RGB").save(REVIEW_ROOT / "sunset_underpass_layer_preview.png", optimize=False)
    five_value_study(preview.convert("RGB")).save(REVIEW_ROOT / "sunset_underpass_value_study.png", optimize=False)

    palette_bytes = bytes(runtime_palette)
    palette_hash = hashlib.sha256(palette_bytes).hexdigest()
    runtime_assets = [
        RUNTIME_ROOT / "background.png",
        *(PANEL_ROOT / f"underpass_{name}.png" for name in PANEL_NAMES),
        *(ART_ROOT / name for name in layer_images),
        *foliage_paths,
        FOLIAGE_MODEL_PATH,
    ]
    asset_hashes = {path.relative_to(ROOT / "openbor/data").as_posix(): sha256(path) for path in runtime_assets}
    fingerprint = hashlib.sha256("".join(f"{key}:{value}" for key, value in sorted(asset_hashes.items())).encode("ascii")).hexdigest()

    preserved_validation = {}
    if MANIFEST_PATH.is_file():
        try:
            existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            if existing.get("asset_set_sha256") == fingerprint:
                preserved_validation = existing.get("runtime_validation", {})
        except (OSError, json.JSONDecodeError):
            pass

    manifest = {
        "schema_version": 3,
        "stage_id": "i8_underpass_sunset_techdemo",
        "display_name": "I-8 Sunset Underpass Tech Demo",
        "engine": "OpenBOR 4.0 Build 7949",
        "maturity": "playable_stage_candidate",
        "one_screen_promise": "Cross cracked wet asphalt from an open coral sunset into a cool compressed overpass core, then emerge toward a wider violet-orange mountain portal.",
        "viewport": [640, 360],
        "world_size": [WORLD_WIDTH, 360],
        "panel_order": "abcd",
        "panel_dimensions": [640, 360],
        "palette_sha256": palette_hash,
        "palette_index_0": "transparent",
        "source_commit": git_head(),
        "source_art": {
            f"panel_{name}": {
                "path": f"content/setpieces/underpass_i8/art_source/sunset_techdemo/panel_{name}_source.png",
                "sha256": sha256(SOURCE_ROOT / f"panel_{name}_source.png"),
                "role": "generated original pixel-art source; concept image used as mood/structure reference only",
            }
            for name in PANEL_NAMES
        },
        "environmental_entity_contract": {
            "name": "UnderpassFoliage",
            "classification": "noninteractive environmental scenery",
            "maturity": "production",
            "exact_unique_pose_target": 3,
            "allocation": {"idle_sway": 3},
            "action_reachability": ["auto-spawned by stage events", "looped idle sway"],
            "controls_ai_combat_collision": "none",
            "runtime_sequence": [1, 2, 3, 2],
        },
        "beat_map": [
            {"panel": "a", "world_x": [0, 639], "beat": "sunset_mouth", "landmark": "angled wing wall and offset pier", "light": "warm approach", "view": "pier gate"},
            {"panel": "b", "world_x": [640, 1279], "beat": "pier_gate", "landmark": "staggered piers and transformer beyond fence", "light": "cool fill with warm slit", "view": "shadow core"},
            {"panel": "c", "world_x": [1280, 1919], "beat": "shadow_core", "landmark": "drainage gate and diagonal conduit", "light": "coolest compression", "view": "exit cue"},
            {"panel": "d", "world_x": [1920, 2559], "beat": "sunset_release", "landmark": "final pier, gate, embankment and mountain portal", "light": "amber release", "view": "sealed end edge"},
        ],
        "layers": [
            {"job": "base", "path": "data/levels/i8_underpass/background.png", "size": [640, 360], "motion": "static palette holder"},
            {"job": "far", "path": "data/levels/i8_underpass/art/far.png", "size": [2048, 360], "xratio": 0.30, "motion": "camera parallax"},
            {"job": "mid", "path": "data/levels/i8_underpass/art/mid.png", "size": [1792, 360], "xratio": 0.60, "motion": "camera parallax"},
            {"job": "panel", "paths": [f"data/levels/i8_underpass/panels/underpass_{name}.png" for name in PANEL_NAMES], "size": [640, 360], "xratio": 0.0, "motion": "world locked"},
            {"job": "haze_effect", "path": "data/levels/i8_underpass/art/haze.png", "size": [2816, 360], "z": 210, "xratio": 0.0, "alpha": 1, "bgspeedratio": 1.0, "motion": "slow horizontal drift behind actors"},
            {"job": "static_pixel_details", "location": "baked into panel plane", "motion": "static", "content": ["pier posters and glyphs", "curb litter", "asphalt cracks and aggregate", "walkable wrappers and crushed cans"]},
            {"job": "rooted_foliage_scenery", "model": "data/levels/i8_underpass/underpass_foliage.txt", "frames": [path.relative_to(ROOT / "openbor/data").as_posix() for path in foliage_paths], "unique_frames": 3, "runtime_sequence": [1, 2, 3, 2], "anchor_z": 248, "world_x": list(FOLIAGE_ROOTS), "motion": "localized hand-drawn lean cycle behind actors; no water distortion"},
        ],
        "geometry": {
            "revision": 1,
            "walkable_floor": {"world_x": [0, 2559], "z": [252, 326], "classification": "walkable"},
            "rear_curb_and_fence": {"z": [246, 251], "classification": "background-only visual boundary; player Z minimum supplies traversal bound"},
            "front_edge": {"z": 326, "classification": "player Z maximum; no painted drop"},
            "puddles_reflections_cracks": {"classification": "walkable decals"},
            "deck_piers_fence_boxes_gate_hills_palms": {"classification": "background-only beyond rear bound"},
            "foliage": {"classification": "non-interactive animated background scenery rooted at the rear curb; behind every player Z lane"},
            "walls": [],
            "holes": [],
            "platforms": [],
            "physical_props": [],
        },
        "runtime_assets": asset_hashes,
        "asset_set_sha256": fingerprint,
        "directives": {
            "video": "video 640x360",
            "level": "data/levels/i8_underpass.txt",
            "background_rule": "single 640x360 indexed background holder; no wide background directive",
        },
        "review_artifacts": [
            "content/setpieces/underpass_i8/review/sunset_techdemo/sunset_underpass_layer_preview.png",
            "content/setpieces/underpass_i8/review/sunset_techdemo/sunset_underpass_value_study.png",
        ],
        "runtime_validation": preserved_validation or {
            "status": "pending_packaged_gameplay",
            "package_sha256": None,
            "package_file_count": None,
            "log": None,
            "evidence": [],
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    manifest = build()
    print(json.dumps({
        "stage": manifest["stage_id"],
        "world_size": manifest["world_size"],
        "panel_order": manifest["panel_order"],
        "asset_set_sha256": manifest["asset_set_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
