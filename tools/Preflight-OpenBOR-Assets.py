"""Fail-fast OpenBOR asset and package compatibility checks."""

from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
REJECTED_DIRECTIVES = {"shadow_coords"}
MODEL_TYPES = {"none", "player", "enemy", "item", "obstacle", "steamer", "projectile", "pshot", "trap", "text", "endlevel", "npc", "panel"}
ENTITY_TYPE_FLAGS = {"none", "enemy", "npc", "obstacle", "player", "projectile", "shot", "text", "trap"}
STATIC_SHADOW_FLAGS = {"default", "graphic_static_air", "graphic_static_ground"}
REPLICA_SHADOW_FLAGS = {"graphic_replica_air", "graphic_replica_ground"}
SHOWCASE_MARKER_PALETTE_INDEX = 102
SHOWCASE_MARKER_PACKED_COLOR = 0x6299F3
PATH_ARGUMENTS = {
    "background": 1,
    "didhitscript": 1,
    "didblockscript": 1,
    "file": 1,
    "frame": 1,
    "levelscript": 1,
    "models": 1,
    "levels": 1,
    "onspawnscript": 1,
    "panel": 1,
    "thinkscript": 1,
    "updatescript": 1,
    "updatedscript": 1,
}


def png_header(path: Path) -> tuple[int, int, int, int, int, int, int]:
    data = path.read_bytes()
    if data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise ValueError(f"{path}: not a valid PNG with an IHDR chunk")
    return struct.unpack(">IIBBBBB", data[16:29])


def check_pngs(data_root: Path) -> list[str]:
    checked: list[str] = []
    for path in sorted(data_root.rglob("*.png")):
        width, height, bit_depth, color_type, compression, filtering, interlace = png_header(path)
        if width <= 0 or height <= 0 or compression != 0 or filtering != 0 or interlace != 0:
            raise ValueError(f"{path}: PNG must be non-interlaced with standard compression/filtering")
        relative = path.relative_to(data_root).as_posix()
        is_panel = relative.startswith("levels/") and "/panels/" in relative
        is_level_background = relative.startswith("levels/") and relative.endswith("/background.png")
        if relative.startswith("chars/") or is_level_background or is_panel:
            if bit_depth != 8 or color_type != 3:
                raise ValueError(
                    f"{path}: character sprites, level backgrounds, and panels must be non-interlaced 8-bit indexed PNGs "
                    f"(bit_depth={bit_depth}, color_type={color_type})"
                )
        elif color_type not in {2, 3, 6}:
            raise ValueError(f"{path}: unsupported PNG color type {color_type}")
        if (is_panel or is_level_background) and (width, height) != (640, 360):
            raise ValueError(f"{path}: Build 7949 tech-demo plates must be exactly 640x360, got {width}x{height}")
        checked.append(relative)
    return checked


def check_video_config(data_root: Path) -> None:
    path = data_root / "video.txt"
    if not path.is_file():
        raise ValueError(f"{path}: required OpenBOR video configuration is missing")
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="strict").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    video_lines = [line for line in lines if line.split(maxsplit=1)[0] == "video"]
    if video_lines != ["video 640x360"]:
        raise ValueError(f"{path}: expected exactly one parser-compatible 'video 640x360' directive")
    for line in lines:
        command = line.split(maxsplit=1)[0]
        if command.startswith("a") and len(command) > 1 and command[1].isdigit():
            raise ValueError(f"{path}: unsupported resolution token '{command}'; use 'video WIDTHxHEIGHT'")


def referenced_path(data_root: Path, source: Path, line_number: int, token: str) -> Path:
    normalized = token.replace("\\", "/")
    if not normalized.startswith("data/") or ".." in Path(normalized).parts:
        raise ValueError(f"{source}:{line_number}: reference must stay under data/: {token}")
    target = data_root / normalized.removeprefix("data/")
    if not target.is_file():
        raise ValueError(f"{source}:{line_number}: referenced file is missing: {token}")
    return target


def check_text_directives(data_root: Path) -> list[str]:
    checked: list[str] = []
    for path in sorted(data_root.rglob("*.txt")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
            tokens = line.strip().split() if line.strip() and not line.lstrip().startswith("#") else []
            command = tokens[0] if tokens else ""
            if command in REJECTED_DIRECTIVES:
                raise ValueError(f"{path}:{line_number}: unsupported OpenBOR directive '{command}'")
            if command == "anim" and len(tokens) > 1 and tokens[1].lower() == "die":
                raise ValueError(f"{path}:{line_number}: Build 7949 model token is 'anim death', not invalid 'anim die'")
            if command == "type" and len(tokens) > 1 and tokens[1].lower() not in MODEL_TYPES:
                raise ValueError(f"{path}:{line_number}: unsupported Build 7949 model type {tokens[1]!r}")
            if command == "candamage" and (len(tokens) < 2 or any(token.lower() not in ENTITY_TYPE_FLAGS for token in tokens[1:])):
                raise ValueError(f"{path}:{line_number}: candamage requires supported Build 7949 entity type names")
            if command in {"load", "know"}:
                if path == data_root / "models.txt":
                    if len(tokens) < 3:
                        raise ValueError(f"{path}:{line_number}: {command} requires a model name and data path")
                    referenced_path(data_root, path, line_number, tokens[2])
                elif command == "load" and len(tokens) > 2 and not tokens[2].replace("-", "", 1).isdigit():
                    raise ValueError(
                        f"{path}:{line_number}: model-local load accepts a cached model name and optional numeric flag, "
                        "not a path; register the model in models.txt"
                    )
            elif command in PATH_ARGUMENTS:
                index = PATH_ARGUMENTS[command]
                if len(tokens) <= index:
                    raise ValueError(f"{path}:{line_number}: {command} is missing its data path")
                referenced_path(data_root, path, line_number, tokens[index])
        checked.append(path.relative_to(data_root).as_posix())
    update = data_root / "scripts" / "update.c"
    if not update.is_file():
        raise ValueError(f"{update}: global update script is required by script.txt")
    return checked


def check_static_shadow_dependencies(data_root: Path) -> None:
    """Reject Build 7949's unchecked static-shadow sprite lookup when its PNG is absent."""
    chars_root = data_root / "chars"
    for path in sorted(chars_root.rglob("*.txt")):
        shadow_index = 0
        static_enabled = True
        replica_enabled = False
        disabled = False
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
            tokens = line.strip().split() if line.strip() and not line.lstrip().startswith("#") else []
            if not tokens:
                continue
            command = tokens[0].lower()
            if command == "shadow":
                if len(tokens) < 2 or not tokens[1].lstrip("-").isdigit():
                    raise ValueError(f"{path}:{line_number}: shadow requires an integer sprite index")
                shadow_index = int(tokens[1])
                if not 0 <= shadow_index <= 6:
                    raise ValueError(f"{path}:{line_number}: Build 7949 supports static shadow indices 0..6")
            elif command == "gfxshadow":
                if len(tokens) < 2 or tokens[1] not in {"0", "1"}:
                    raise ValueError(f"{path}:{line_number}: gfxshadow requires 0 or 1")
                replica_enabled = tokens[1] == "1"
                static_enabled = not replica_enabled
            elif command == "shadow_config":
                flags = {token.lower() for token in tokens[1:]}
                disabled = "disabled" in flags
                static_enabled = bool(flags & STATIC_SHADOW_FLAGS)
                replica_enabled = bool(flags & REPLICA_SHADOW_FLAGS)

        if shadow_index and static_enabled and not replica_enabled and not disabled:
            required = data_root / "sprites" / f"shadow{shadow_index}.png"
            if not required.is_file():
                raise ValueError(
                    f"{path}: static shadow {shadow_index} requires {required}; Build 7949 otherwise "
                    "dereferences an invalid sprite during entity rendering. Use a packaged sprite, gfxshadow 1, or shadow 0."
                )


def split_call_arguments(payload: str) -> list[str]:
    arguments: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False
    for index, char in enumerate(payload):
        if escaped:
            escaped = False
            continue
        if quote:
            if char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            arguments.append(payload[start:index].strip())
            start = index + 1
    arguments.append(payload[start:].strip())
    return arguments


def check_scripts(data_root: Path) -> list[str]:
    checked: list[str] = []
    loaded_scripts: set[Path] = {data_root / "scripts" / "update.c"}
    for path in sorted(data_root.rglob("*.txt")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
            tokens = line.strip().split() if line.strip() and not line.lstrip().startswith("#") else []
            if tokens and tokens[0] in {"didhitscript", "didblockscript", "onspawnscript", "thinkscript", "updatescript", "updatedscript", "levelscript"} and len(tokens) > 1:
                loaded_scripts.add(referenced_path(data_root, path, line_number, tokens[1]))
    for path in sorted(data_root.rglob("*.c")):
        payload = path.read_text(encoding="utf-8", errors="strict")
        if path in loaded_scripts and len(re.findall(r"\bvoid\s+main\s*\(\s*\)", payload)) != 1:
            raise ValueError(f"{path}: every loaded Build 7949 event script requires exactly one void main() entry")
        for match in re.finditer(r"\blog\s*\((.*?)\)\s*;", payload, flags=re.DOTALL):
            arguments = split_call_arguments(match.group(1))
            if len(arguments) != 1:
                line = payload.count("\n", 0, match.start()) + 1
                raise ValueError(f"{path}:{line}: Build 7949 log() accepts exactly one argument")
        checked.append(path.relative_to(data_root).as_posix())
    return checked


def check_tech_demo_contract(data_root: Path) -> None:
    level = data_root / "levels" / "entity_combat_tech_demo.txt"
    payload = level.read_text(encoding="utf-8", errors="strict")
    if "levelscript data/scripts/entity_tech_demo.c" in payload:
        raise ValueError(f"{level}: levelscript runs once; deterministic harness requires updatescript")
    if payload.count("updatescript data/scripts/entity_tech_demo.c") != 1:
        raise ValueError(f"{level}: expected exactly one deterministic updatescript")
    if payload.count("updatedscript data/scripts/entity_pose_overlay.c") != 1:
        raise ValueError(f"{level}: expected exactly one post-entity pose overlay")
    if re.search(r"^\s*(?:background|bglayer|fglayer|layer)\s+", payload, flags=re.MULTILINE):
        raise ValueError(f"{level}: Build 7949 free-walk demo must be panel-only; backdrop layers are forbidden")
    panels = re.findall(r"^panel\s+(\S+)$", payload, flags=re.MULTILINE)
    expected_panels = [f"data/levels/i8_underpass/panels/underpass_{letter}.png" for letter in "abcd"]
    if panels != expected_panels or "order abcd" not in payload:
        raise ValueError(f"{level}: expected exactly four ordered 640x360 panel assets")
    panel_palettes: list[bytes] = []
    panel_pixels: list[bytes] = []
    panel_edges: list[tuple[bytes, bytes]] = []
    for panel in expected_panels:
        with Image.open(data_root / panel.removeprefix("data/")) as image:
            if image.mode != "P" or image.size != (640, 360):
                raise ValueError(f"{panel}: panel-only tech demo requires an indexed 640x360 image")
            palette = image.getpalette()
            pixels = image.tobytes()
            left_edge = image.crop((0, 0, 1, 360)).tobytes()
            right_edge = image.crop((639, 0, 640, 360)).tobytes()
        if palette is None:
            raise ValueError(f"{panel}: indexed panel has no palette")
        transparent_pixels = pixels.count(0)
        if transparent_pixels:
            raise ValueError(
                f"{panel}: panel-only tech demo exposes {transparent_pixels} transparent index-0 pixels; "
                "Build 7949 will render the uncovered portal as a black void"
            )
        panel_palettes.append(bytes((palette + [0] * 768)[:768]))
        panel_pixels.append(pixels)
        panel_edges.append((left_edge, right_edge))
    if any(palette != panel_palettes[0] for palette in panel_palettes[1:]):
        raise ValueError(f"{level}: all panel-only tech-demo plates must share one identical palette")
    if len(set(panel_pixels)) != len(panel_pixels):
        raise ValueError(f"{level}: all four ordered panel-only tech-demo plates must be pixel-unique")
    for index in range(len(panel_edges) - 1):
        if panel_edges[index][1] != panel_edges[index + 1][0]:
            mismatch_count = sum(
                left != right for left, right in zip(panel_edges[index][1], panel_edges[index + 1][0])
            )
            raise ValueError(
                f"{level}: panel seam {expected_panels[index]} -> {expected_panels[index + 1]} "
                f"has {mismatch_count} mismatched rows"
            )
    system_palette = (data_root / "pal.act").read_bytes()
    if len(system_palette) != 768 or system_palette[:384] != panel_palettes[0][:384]:
        raise ValueError(
            f"{data_root / 'pal.act'}: panel-only Build 7949 demo must copy panel palette indices 0..127 "
            "because no background is loaded to initialize the system palette"
        )
    marker_rgb = system_palette[SHOWCASE_MARKER_PALETTE_INDEX * 3 : SHOWCASE_MARKER_PALETTE_INDEX * 3 + 3]
    marker_luma = (299 * marker_rgb[0] + 587 * marker_rgb[1] + 114 * marker_rgb[2]) / 1000
    if marker_luma < 128:
        raise ValueError(
            f"{data_root / 'pal.act'}: showcase marker index {SHOWCASE_MARKER_PALETTE_INDEX} "
            f"must be visibly bright, got RGB {tuple(marker_rgb)}"
        )
    overlay = data_root / "scripts" / "entity_pose_overlay.c"
    overlay_payload = overlay.read_text(encoding="utf-8", errors="strict")
    if overlay_payload.count(str(SHOWCASE_MARKER_PACKED_COLOR)) != 4:
        raise ValueError(
            f"{overlay}: PIXEL_32 showcase barcode must use packed BGR color "
            f"0x{SHOWCASE_MARKER_PACKED_COLOR:06X} exactly four times"
        )
    spawn_data: dict[str, tuple[int, int, int, int]] = {}
    current_model: str | None = None
    current_coords: tuple[int, int, int] | None = None
    for line_number, line in enumerate(payload.splitlines(), 1):
        tokens = line.strip().split() if line.strip() and not line.lstrip().startswith("#") else []
        if not tokens:
            continue
        if tokens[0] == "spawn" and len(tokens) == 2:
            current_model = tokens[1]
            current_coords = None
        elif current_model and tokens[0] == "coords" and len(tokens) == 4:
            current_coords = tuple(int(value) for value in tokens[1:])
        elif current_model and tokens[0] == "at" and len(tokens) == 2:
            if current_coords is not None:
                spawn_data[current_model] = (*current_coords, int(tokens[1]))
            current_model = None
            current_coords = None

    for runtime_name, directory in {
        "HomelessMan": "homeless_man",
        "PoliceOfficer": "police_officer",
    }.items():
        if runtime_name not in spawn_data:
            raise ValueError(f"{level}: missing {runtime_name} spawn coordinates")
        x, z, altitude, at = spawn_data[runtime_name]
        if at != 0:
            raise ValueError(f"{level}: {runtime_name} visibility audit requires initial 'at 0' spawn")
        bounds: list[tuple[int, int, int, int]] = []
        for sprite in sorted((data_root / "chars" / directory / "sprites").glob("*.png")):
            with Image.open(sprite) as image:
                bbox = image.getbbox()
            if bbox is not None:
                bounds.append(bbox)
        if not bounds:
            raise ValueError(f"{level}: no runtime sprites available for {runtime_name} visibility audit")
        left = min(box[0] for box in bounds)
        top = min(box[1] for box in bounds)
        right = max(box[2] for box in bounds) - 1
        bottom = max(box[3] for box in bounds) - 1
        root_x, root_y = 96, 156
        horizontal_radius = max(abs(left - root_x), abs(right - root_x))
        screen_left = x - horizontal_radius
        screen_right = x + horizontal_radius
        screen_top = z - altitude + top - root_y
        screen_bottom = z - altitude + bottom - root_y
        if screen_left < 0 or screen_right >= 640 or screen_top < 0 or screen_bottom >= 360:
            raise ValueError(
                f"{level}: {runtime_name} spawn {(x, z, altitude)} clips authored sprites in 640x360; "
                f"safe extent is x={screen_left}..{screen_right}, y={screen_top}..{screen_bottom}"
            )
    levels = (data_root / "levels.txt").read_text(encoding="utf-8", errors="strict")
    if levels.count("skiptoset 0") != 1:
        raise ValueError(f"{data_root / 'levels.txt'}: direct tech demo requires exactly one 'skiptoset 0'")
    if levels.count("file data/levels/entity_combat_tech_demo.txt") != 1:
        raise ValueError(f"{data_root / 'levels.txt'}: package must register only the entity tech demo")
    if re.search(r"^file\s+(?!data/levels/entity_combat_tech_demo\.txt$)", levels, flags=re.MULTILINE):
        raise ValueError(f"{data_root / 'levels.txt'}: stale or unrelated levels are forbidden in this package profile")


def check_pack(source_root: Path, pak_path: Path) -> int:
    payload = pak_path.read_bytes()
    if payload[:4] != b"PACK" or len(payload) < 12:
        raise ValueError(f"{pak_path}: invalid PACK header")
    format_id = struct.unpack_from("<I", payload, 4)[0]
    if format_id != 0:
        raise ValueError(f"{pak_path}: expected PAK32 format id 0, got {format_id}")
    table_offset = struct.unpack_from("<I", payload, len(payload) - 4)[0]
    if not 8 <= table_offset < len(payload) - 4:
        raise ValueError(f"{pak_path}: invalid table offset {table_offset}")
    expected = {
        ("data\\" + path.relative_to(source_root).as_posix().replace("/", "\\")).encode("ascii")
        : path.read_bytes()
        for path in source_root.rglob("*")
        if path.is_file()
    }
    seen: set[bytes] = set()
    cursor = table_offset
    while cursor < len(payload) - 4:
        if cursor + 12 > len(payload):
            raise ValueError(f"{pak_path}: truncated package table")
        record_size, offset, size = struct.unpack_from("<III", payload, cursor)
        if record_size < 13 or cursor + record_size > len(payload) - 4:
            raise ValueError(f"{pak_path}: invalid package record at {cursor}")
        name_end = payload.find(b"\0", cursor + 12, cursor + record_size)
        if name_end < 0:
            raise ValueError(f"{pak_path}: unterminated package filename at {cursor}")
        name = payload[cursor + 12 : name_end]
        if name in seen or name not in expected:
            raise ValueError(f"{pak_path}: unexpected or duplicate entry {name!r}")
        if offset + size > table_offset or payload[offset : offset + size] != expected[name]:
            raise ValueError(f"{pak_path}: payload mismatch for {name.decode('ascii', 'replace')}")
        seen.add(name)
        cursor += record_size
    if seen != set(expected):
        missing = sorted(set(expected) - seen)
        raise ValueError(f"{pak_path}: missing source entries, first={missing[:3]}")
    return len(seen)


def runtime_closure(data_root: Path) -> set[Path]:
    """Resolve the transitive data-file closure from Build 7949 registries."""
    queue = [data_root / "levels.txt", data_root / "models.txt", data_root / "script.txt"]
    closure = {
        data_root / "levels.txt",
        data_root / "models.txt",
        data_root / "lifebar.txt",
        data_root / "pal.act",
        data_root / "script.txt",
        data_root / "video.txt",
    }
    seen_text: set[Path] = set()
    while queue:
        source = queue.pop()
        if source in seen_text:
            continue
        seen_text.add(source)
        for line_number, line in enumerate(source.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
            tokens = line.strip().split() if line.strip() and not line.lstrip().startswith("#") else []
            if not tokens:
                continue
            command = tokens[0]
            target: Path | None = None
            if command in {"load", "know"} and source == data_root / "models.txt" and len(tokens) >= 3:
                target = referenced_path(data_root, source, line_number, tokens[2])
            elif command in PATH_ARGUMENTS and len(tokens) > PATH_ARGUMENTS[command]:
                target = referenced_path(data_root, source, line_number, tokens[PATH_ARGUMENTS[command]])
            if target is not None:
                closure.add(target)
                if target.suffix.lower() == ".txt":
                    queue.append(target)
    update = data_root / "scripts" / "update.c"
    closure.add(update)
    script_queue = [path for path in closure if path.suffix.lower() == ".c"]
    seen_scripts: set[Path] = set()
    while script_queue:
        script = script_queue.pop()
        if script in seen_scripts:
            continue
        seen_scripts.add(script)
        payload = script.read_text(encoding="utf-8", errors="strict")
        for match in re.finditer(r'\bloadscript\s*\([^,]+,\s*"(data/[^"\r\n]+)"\s*\)', payload):
            target = referenced_path(data_root, script, payload.count("\n", 0, match.start()) + 1, match.group(1))
            closure.add(target)
            if target.suffix.lower() == ".c":
                script_queue.append(target)
    for model in [path for path in closure if path.suffix.lower() == ".txt" and "chars" in path.parts]:
        for line_number, line in enumerate(model.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
            tokens = line.strip().split() if line.strip() and not line.lstrip().startswith("#") else []
            if tokens and tokens[0] == "frame" and len(tokens) > 1:
                closure.add(referenced_path(data_root, model, line_number, tokens[1]))
    return closure


def check_exact_closure(data_root: Path) -> int:
    expected = runtime_closure(data_root)
    actual = {path for path in data_root.rglob("*") if path.is_file()}
    if actual != expected:
        extra = sorted(path.relative_to(data_root).as_posix() for path in actual - expected)
        missing = sorted(path.relative_to(data_root).as_posix() for path in expected - actual)
        raise ValueError(f"{data_root}: package staging is not exact dependency closure; extra={extra[:8]}, missing={missing[:8]}")
    return len(expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("openbor/data"))
    parser.add_argument("--pak", type=Path)
    parser.add_argument("--exact-closure", action="store_true")
    args = parser.parse_args()
    data_root = args.data.resolve()
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("Validate-OpenBOR-Entities.py")), "--stage", "implementation"],
        check=True,
    )
    pngs = check_pngs(data_root)
    check_video_config(data_root)
    text_files = check_text_directives(data_root)
    check_static_shadow_dependencies(data_root)
    scripts = check_scripts(data_root)
    check_tech_demo_contract(data_root)
    closure = check_exact_closure(data_root) if args.exact_closure or args.pak else None
    entries = check_pack(data_root, args.pak.resolve()) if args.pak else None
    if entries is not None and closure != entries:
        raise ValueError(f"package entry count {entries} != dependency closure {closure}")
    print({"status": "pass", "pngs": len(pngs), "text_files": len(text_files), "scripts": len(scripts), "closure": closure, "pak_entries": entries})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
