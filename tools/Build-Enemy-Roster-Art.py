"""Register the approved enemy-roster pose references as native source cels.

The approved references contain seven complete, painterly pixel-art poses on a
flat magenta key.  This tool removes only that key, crops each fixed source
slot, and fits the complete cel into the existing 160x128 enemy contract using
nearest-neighbour resampling.  It never reconstructs clothes, hands, weapons,
or effects from runtime bounds.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
from PIL import Image, ImageChops, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CELL_SIZE = (160, 128)
ROOT = (80, 118)
SOURCE_KEYS = ("ready", "walk_a", "walk_b", "windup", "active", "hurt", "down")
AUTHORED_LANDMARKS_PATH = PROJECT_ROOT / "assets" / "sprites" / "enemies" / "enemy_variant_landmarks.json"
AUTHORED_DROPPED_GEAR_SEPARATOR_POINTS: dict[tuple[str, str], tuple[tuple[int, int], ...]] = {
    # Generated black ground shadows touch these visibly detached props by a
    # thin bridge after nearest-neighbour registration. These reviewed min-cut
    # pixels remove only that bridge; a one-pixel radius survives the small
    # rooted runtime affine without slicing across the actor or prop.
    ("encampment_tire_slinger", "down"): ((118, 95), (115, 96)),
    ("underpass_tire_runner", "down"): (
        (122, 98), (128, 98), (129, 98), (122, 99), (125, 99), (126, 99),
        (127, 99), (128, 99), (122, 100), (123, 100), (124, 100), (125, 100),
    ),
}
AUTHORED_DROPPED_GEAR_SEPARATOR_RECTS: dict[tuple[str, str], tuple[int, int, int, int]] = {
    # The city baton lies along the floor directly under the hand/torso shadow.
    ("city_patrol_nightstick", "down"): (47, 105, 87, 107),
}


@dataclass(frozen=True, slots=True)
class ActorSpec:
    actor: str
    role: str
    weapon: str


ACTORS: tuple[ActorSpec, ...] = (
    ActorSpec("encampment_bottle_scarf", "homeless", "glass_bottle"),
    ActorSpec("encampment_bottle_puffer", "homeless", "glass_bottle"),
    ActorSpec("encampment_tire_slinger", "homeless", "bike_tire"),
    ActorSpec("underpass_tire_runner", "homeless", "bike_tire"),
    ActorSpec("cart_tent_bottle_pitcher", "homeless", "glass_bottle"),
    ActorSpec("mall_security_watch", "security", "flashlight"),
    ActorSpec("event_security_heavy", "security", "flashlight"),
    ActorSpec("night_security_patrol", "security", "flashlight"),
    ActorSpec("city_patrol_nightstick", "police", "nightstick"),
    ActorSpec("transit_patrol_nightstick", "police", "nightstick"),
    ActorSpec("riot_line_nightstick", "police", "nightstick"),
    ActorSpec("bike_patrol_taser", "police", "taser"),
    ActorSpec("tactical_taser_unit", "police", "taser"),
)


def _remove_chroma_key(source: Image.Image) -> Image.Image:
    """Remove the flat magenta plate without palette-quantizing the actor."""

    image = source.convert("RGBA")
    pixels: list[tuple[int, int, int, int]] = []
    for red, green, blue, alpha in image.get_flattened_data():
        # Generated source plates vary by a few values around FF00FF.  The
        # subjects avoid this hue, so a narrow magenta wedge is deterministic
        # and preserves the thousands of opaque material colors byte-for-byte.
        magenta = red >= 175 and blue >= 175 and green <= 145 and abs(red - blue) <= 88
        if magenta:
            pixels.append((0, 0, 0, 0))
            continue
        # The pre-tent atlas contains no key-magenta material. Remove the
        # narrow mixed-color fringe left by generated edge pixels as key plate,
        # too. Keeping it opaque (even recolored) can invisibly bridge a body
        # to dropped gear and corrupt both component and anchor semantics.
        residual_key = (
            red >= 120
            and blue >= 100
            and green * 2 < min(red, blue)
            and abs(red - blue) <= 80
        )
        if residual_key:
            pixels.append((0, 0, 0, 0))
            continue
        pixels.append((red, green, blue, alpha))
    image.putdata(pixels)
    return image


def _mask_for(image: Image.Image) -> pygame.mask.Mask:
    surface = pygame.image.frombytes(image.tobytes(), image.size, "RGBA")
    return pygame.mask.from_surface(surface, threshold=7)


def _mask_alpha(mask: pygame.mask.Mask) -> Image.Image:
    surface = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    rgba = Image.frombytes("RGBA", mask.get_size(), pygame.image.tobytes(surface, "RGBA"))
    return rgba.getchannel("A")


def _rect_distance(first: pygame.Rect, second: pygame.Rect) -> int:
    dx = max(first.left - second.right, second.left - first.right, 0)
    dy = max(first.top - second.bottom, second.top - first.bottom, 0)
    return dx * dx + dy * dy


def _source_slots(path: Path) -> list[Image.Image]:
    if not path.is_file():
        raise FileNotFoundError(f"missing approved enemy pose reference: {path}")
    sheet = Image.open(path).convert("RGBA")
    # The approved render service preserves one seven-slot row but may trim
    # unused plate margins.  Slot positions remain equal fractions of the
    # final plate, so retain those authored divisions instead of rescaling the
    # full reference before extraction.
    if sheet.width < 1400 or sheet.height < 600:
        raise ValueError(f"{path.name} is too small for seven source slots: {sheet.size}")
    keyed_sheet = _remove_chroma_key(sheet)
    components = _mask_for(keyed_sheet).connected_components(3)
    components = [component for component in components if component.count() >= 3]
    if len(components) < len(SOURCE_KEYS):
        raise ValueError(f"{path.name} exposes only {len(components)} connected drawings")

    # The seven largest connected drawings are the seven complete bodies.
    # Detached held/dropped gear is much smaller and is assigned spatially to
    # its closest body. This handles the hurt/down overlap where no vertical
    # gutter exists and prevents a neighbouring head or shoe entering a cel.
    bodies = sorted(components, key=lambda component: component.count(), reverse=True)[: len(SOURCE_KEYS)]
    bodies.sort(key=lambda component: component.centroid()[0])
    body_ids = {id(component) for component in bodies}
    extras_by_body: list[list[pygame.mask.Mask]] = [[] for _ in bodies]
    body_rects = [component.get_bounding_rects()[0] for component in bodies]
    for component in components:
        if id(component) in body_ids or component.count() < 80:
            continue
        rect = component.get_bounding_rects()[0]
        body_index = min(range(len(bodies)), key=lambda index: _rect_distance(rect, body_rects[index]))
        if _rect_distance(rect, body_rects[body_index]) <= 180 * 180:
            extras_by_body[body_index].append(component)

    slots: list[Image.Image] = []
    for index, body in enumerate(bodies):
        group = body.copy()
        # Keep at most one detached authored prop. Tiny edge components and
        # foreign fragments are rejected; held gear touching a hand is already
        # part of the main body component.
        if extras_by_body[index]:
            prop = max(extras_by_body[index], key=lambda component: component.count())
            group.draw(prop, (0, 0))
        clean = keyed_sheet.copy()
        clean.putalpha(ImageChops.multiply(clean.getchannel("A"), _mask_alpha(group)))
        bounds = clean.getchannel("A").getbbox()
        if bounds is None:
            raise ValueError(f"{path.name} source slot {index} is empty after chroma key")
        slots.append(clean.crop(bounds))
    return slots


def _registered_cels(path: Path) -> list[Image.Image]:
    sprites = _source_slots(path)
    max_width = max(sprite.width for sprite in sprites)
    max_height = max(sprite.height for sprite in sprites)
    scale = min(156 / max_width, 116 / max_height)
    if not (0.20 <= scale <= 0.65):
        raise ValueError(f"{path.name} requires suspicious registration scale {scale:.3f}")
    cels: list[Image.Image] = []
    for key, sprite in zip(SOURCE_KEYS, sprites, strict=True):
        width = max(1, round(sprite.width * scale))
        height = max(1, round(sprite.height * scale))
        resized = sprite.resize((width, height), Image.Resampling.NEAREST)
        cel = Image.new("RGBA", CELL_SIZE, (0, 0, 0, 0))
        x = ROOT[0] - width // 2
        y = ROOT[1] - height
        if x < 2 or x + width > CELL_SIZE[0] - 2 or y < 2:
            raise ValueError(f"{path.name}:{key} does not fit native cell: {(x, y, width, height)}")
        cel.alpha_composite(resized, (x, y))
        cels.append(cel)
    return cels


def _separate_authored_dropped_gear(actor: str, key: str, cel: Image.Image) -> Image.Image:
    points = AUTHORED_DROPPED_GEAR_SEPARATOR_POINTS.get((actor, key), ())
    rectangle = AUTHORED_DROPPED_GEAR_SEPARATOR_RECTS.get((actor, key))
    if not points and rectangle is None:
        return cel
    separated = cel.copy()
    draw = ImageDraw.Draw(separated)
    for x, y in points:
        draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=(0, 0, 0, 0))
    if rectangle is not None:
        draw.rectangle(rectangle, fill=(0, 0, 0, 0))
    return separated


def _distance_to_alpha(cel: Image.Image, point: tuple[int, int]) -> float:
    alpha = cel.getchannel("A")
    px = alpha.load()
    visible = [
        (x, y)
        for y in range(CELL_SIZE[1])
        for x in range(CELL_SIZE[0])
        if px[x, y] >= 16
    ]
    if not visible:
        raise ValueError("cannot anchor an empty enemy cel")
    return min(
        ((candidate[0] - point[0]) ** 2 + (candidate[1] - point[1]) ** 2) ** 0.5
        for candidate in visible
    )


def _point(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(item, int) for item in value):
        raise ValueError(f"{label} must be a two-integer cell-local point")
    point = (value[0], value[1])
    if not (0 <= point[0] < CELL_SIZE[0] and 0 <= point[1] < CELL_SIZE[1]):
        raise ValueError(f"{label} escapes the 160x128 cell: {point}")
    return point


def _source_metadata(
    spec: ActorSpec,
    key: str,
    cel: Image.Image,
    authored: dict[str, object],
) -> dict[str, object]:
    """Validate and return frozen, reviewed landmarks without deriving them."""

    bounds = cel.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"{spec.actor}:{key} is empty")
    if bounds[0] < 2 or bounds[1] < 2 or bounds[2] > CELL_SIZE[0] - 2 or bounds[3] > CELL_SIZE[1] - 2:
        raise ValueError(f"{spec.actor}:{key} violates the two-pixel cell inset: {bounds}")
    magenta = sum(
        alpha >= 8
        and red >= 120
        and blue >= 100
        and green * 2 < min(red, blue)
        and abs(red - blue) <= 80
        for red, green, blue, alpha in cel.get_flattened_data()
    )
    if magenta:
        raise ValueError(f"{spec.actor}:{key} retains {magenta} visible key-magenta pixels")

    root = _point(authored.get("root"), f"{spec.actor}:{key}:root")
    rear = _point(authored.get("rear_hand"), f"{spec.actor}:{key}:rear_hand")
    lead = _point(authored.get("lead_hand"), f"{spec.actor}:{key}:lead_hand")
    weapon_value = authored.get("weapon_anchor")
    weapon_anchor = None if weapon_value is None else _point(weapon_value, f"{spec.actor}:{key}:weapon_anchor")
    release_value = authored.get("release_anchor")
    release_anchor = None if release_value is None else _point(release_value, f"{spec.actor}:{key}:release_anchor")
    if root != ROOT:
        raise ValueError(f"{spec.actor}:{key} root must remain the fixed {ROOT}, got {root}")
    lowest_alpha = bounds[3] - 1
    if not 0 <= root[1] - lowest_alpha <= 4:
        raise ValueError(f"{spec.actor}:{key} root {root} is not registered to alpha bottom {lowest_alpha}")
    for label, point in (("rear_hand", rear), ("lead_hand", lead)):
        distance = _distance_to_alpha(cel, point)
        if distance > 4.0:
            raise ValueError(f"{spec.actor}:{key}:{label} misses visible alpha by {distance:.2f}px")
    if weapon_anchor is not None and _distance_to_alpha(cel, weapon_anchor) > 4.0:
        raise ValueError(f"{spec.actor}:{key}:weapon_anchor misses authored gear")
    if release_anchor is not None and min(
        ((release_anchor[0] - hand[0]) ** 2 + (release_anchor[1] - hand[1]) ** 2) ** 0.5
        for hand in (rear, lead)
    ) > 18.0:
        raise ValueError(f"{spec.actor}:{key}:release_anchor is detached from both authored hands")

    component_count = len([
        component
        for component in _mask_for(cel).connected_components(3)
        if component.count() >= 20
    ])
    if not 1 <= component_count <= 2:
        raise ValueError(f"{spec.actor}:{key} has {component_count} production components")
    held_gear = bool(authored.get("held_gear"))
    if held_gear and weapon_anchor is None:
        raise ValueError(f"{spec.actor}:{key} marks held gear without a weapon anchor")
    frozen_count = authored.get("component_count")
    if frozen_count is not None and frozen_count != component_count:
        raise ValueError(
            f"{spec.actor}:{key} component count drifted from reviewed {frozen_count} to {component_count}"
        )
    return {
        "root": list(root),
        "rear_hand": list(rear),
        "lead_hand": list(lead),
        "weapon_anchor": list(weapon_anchor) if weapon_anchor is not None else None,
        "release_anchor": list(release_anchor) if release_anchor is not None else None,
        "held_gear": held_gear,
        "gear_state": str(authored.get("gear_state")),
        "component_count": component_count,
    }


def _marker(draw: ImageDraw.ImageDraw, point: list[int] | None, color: tuple[int, int, int, int]) -> None:
    if point is None:
        return
    x, y = point
    draw.line((x - 3, y, x + 3, y), fill=(10, 10, 12, 255), width=3)
    draw.line((x, y - 3, x, y + 3), fill=(10, 10, 12, 255), width=3)
    draw.line((x - 2, y, x + 2, y), fill=color, width=1)
    draw.line((x, y - 2, x, y + 2), fill=color, width=1)


def _load_authored_landmarks(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"missing reviewed enemy landmark table: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or payload.get("cell_size") != list(CELL_SIZE):
        raise ValueError(f"unsupported enemy landmark table contract: {path}")
    actors = payload.get("actors")
    if not isinstance(actors, dict) or set(actors) != {spec.actor for spec in ACTORS}:
        raise ValueError(f"enemy landmark table actor set does not match the roster: {path}")
    for spec in ACTORS:
        source_keys = actors[spec.actor].get("source_keys")
        if not isinstance(source_keys, dict) or tuple(source_keys) != SOURCE_KEYS:
            raise ValueError(f"{spec.actor} landmark source-key order must be {SOURCE_KEYS}")
    return payload


def _qa_sheet(
    cels_by_actor: dict[str, list[Image.Image]],
    actors_metadata: dict[str, object],
    destination: Path,
    *,
    show_anchors: bool,
) -> None:
    label_width = 220
    top = 56 if show_anchors else 32
    row_height = CELL_SIZE[1] + 6
    sheet = Image.new("RGB", (label_width + CELL_SIZE[0] * len(SOURCE_KEYS), top + row_height * len(ACTORS)), (24, 26, 31))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    title = "ENEMY ROSTER - AUTHORED ANCHOR DIAGNOSTIC" if show_anchors else "ENEMY ROSTER - CLEAN PRODUCTION CELS"
    draw.text((8, 8), title, fill=(245, 220, 120), font=font)
    if show_anchors:
        draw.text(
            (8, 23),
            "QA MARKERS ONLY: root=green rear=cyan lead=yellow weapon=orange release=magenta",
            fill=(199, 205, 217),
            font=font,
        )
    column_label_y = 40 if show_anchors else 20
    for column, key in enumerate(SOURCE_KEYS):
        draw.text(
            (label_width + column * CELL_SIZE[0] + 4, column_label_y),
            key,
            fill=(235, 218, 145),
            font=font,
        )
    for row, spec in enumerate(ACTORS):
        y0 = top + row * row_height
        draw.text((8, y0 + 52), spec.actor, fill=(232, 235, 240), font=font)
        for column, cel in enumerate(cels_by_actor[spec.actor]):
            checker = Image.new("RGBA", CELL_SIZE, (43, 46, 53, 255))
            checker_draw = ImageDraw.Draw(checker)
            for cy in range(0, CELL_SIZE[1], 8):
                for cx in range(0, CELL_SIZE[0], 8):
                    if (cx // 8 + cy // 8) % 2:
                        checker_draw.rectangle((cx, cy, cx + 7, cy + 7), fill=(50, 53, 61, 255))
            checker.alpha_composite(cel)
            key = SOURCE_KEYS[column]
            anchors = actors_metadata[spec.actor]["source_keys"][key]
            if show_anchors:
                _marker(checker_draw, anchors["root"], (78, 224, 124, 255))
                _marker(checker_draw, anchors["rear_hand"], (81, 205, 235, 255))
                _marker(checker_draw, anchors["lead_hand"], (245, 214, 72, 255))
                _marker(checker_draw, anchors["weapon_anchor"], (245, 141, 51, 255))
                _marker(checker_draw, anchors["release_anchor"], (238, 77, 194, 255))
            checker_draw.rectangle((0, 0, CELL_SIZE[0] - 1, CELL_SIZE[1] - 1), outline=(105, 112, 126, 255), width=1)
            sheet.paste(checker.convert("RGB"), (label_width + column * CELL_SIZE[0], y0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, optimize=True)
    print(f"Wrote {destination.relative_to(PROJECT_ROOT)}")


def build(
    output_root: Path,
    source_root: Path,
    landmarks_path: Path,
    qa_output: Path,
    anchor_qa_output: Path,
) -> dict[str, object]:
    output_dir = output_root / "assets" / "sprites" / "enemies"
    output_dir.mkdir(parents=True, exist_ok=True)
    actors_metadata: dict[str, object] = {}
    cels_by_actor: dict[str, list[Image.Image]] = {}
    landmarks = _load_authored_landmarks(landmarks_path)
    for spec in ACTORS:
        reference = source_root / f"{spec.actor}_pose_reference.png"
        cels = _registered_cels(reference)
        cels_by_actor[spec.actor] = cels
        atlas = Image.new("RGBA", (CELL_SIZE[0] * len(SOURCE_KEYS), CELL_SIZE[1]), (0, 0, 0, 0))
        source_keys: dict[str, object] = {}
        signatures: set[bytes] = set()
        for index, (key, cel) in enumerate(zip(SOURCE_KEYS, cels, strict=True)):
            cel = _separate_authored_dropped_gear(spec.actor, key, cel)
            cels[index] = cel
            if cel.tobytes() in signatures:
                raise ValueError(f"{spec.actor}:{key} repeats an earlier complete cel")
            signatures.add(cel.tobytes())
            atlas.alpha_composite(cel, (index * CELL_SIZE[0], 0))
            authored = landmarks["actors"][spec.actor]["source_keys"][key]
            source_keys[key] = {"index": index, **_source_metadata(spec, key, cel, authored)}
        filename = f"{spec.actor}_source_atlas.png"
        destination = output_dir / filename
        atlas.save(destination, optimize=True)
        actors_metadata[spec.actor] = {
            "role": spec.role,
            "weapon": spec.weapon,
            "reference": reference.relative_to(PROJECT_ROOT).as_posix(),
            "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "source_atlas": f"assets/sprites/enemies/{filename}",
            "source_keys": source_keys,
        }
        print(f"Wrote {destination.relative_to(output_root)}: {atlas.width}x{atlas.height}, 7 complete cels")
    metadata = {
        "version": 1,
        "authoring": "approved_complete_whole_cels",
        "cell_size": list(CELL_SIZE),
        "root": list(ROOT),
        "source_keys": list(SOURCE_KEYS),
        "landmark_source": landmarks_path.relative_to(PROJECT_ROOT).as_posix(),
        "actors": actors_metadata,
    }
    metadata_path = output_dir / "enemy_variant_source_anchors.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {metadata_path.relative_to(output_root)}: {len(ACTORS)} actors")
    _qa_sheet(cels_by_actor, actors_metadata, qa_output, show_anchors=False)
    _qa_sheet(cels_by_actor, actors_metadata, anchor_qa_output, show_anchors=True)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--source-root", type=Path, default=PROJECT_ROOT / "art_source" / "enemy_roster")
    parser.add_argument("--landmarks", type=Path, default=AUTHORED_LANDMARKS_PATH)
    parser.add_argument("--qa-output", type=Path, default=PROJECT_ROOT / "build" / "enemy_roster_authored_source_contact.png")
    parser.add_argument("--anchor-qa-output", type=Path, default=PROJECT_ROOT / "build" / "enemy_roster_authored_anchor_qa.png")
    args = parser.parse_args()
    build(
        args.output_root.resolve(),
        args.source_root.resolve(),
        args.landmarks.resolve(),
        args.qa_output.resolve(),
        args.anchor_qa_output.resolve(),
    )


if __name__ == "__main__":
    main()
