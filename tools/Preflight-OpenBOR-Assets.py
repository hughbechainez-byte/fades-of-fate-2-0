"""Fail-fast OpenBOR asset and package compatibility checks."""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
from pathlib import Path, PurePosixPath

from PIL import Image


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
REJECTED_DIRECTIVES = {"shadow_coords"}
I8_UNDERPASS_LEVEL = PurePosixPath("levels/i8_underpass.txt")
STAGE_IMAGE_SIZE = (640, 360)
UNDERPASS_FOLIAGE_FRAME_SIZE = (48, 40)
LAYER_MAX_ARGUMENTS = {
    "bglayer": 18,  # path plus the 17 Build 7949 background-layer properties
    "layer": 19,  # path, Z, plus the 17 shared layer properties
    "fglayer": 19,  # path, Z, plus the 17 shared layer properties
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
        if relative.startswith("chars/") or (relative.startswith("levels/") and relative.endswith("/background.png")):
            if bit_depth != 8 or color_type != 3:
                raise ValueError(
                    f"{path}: character sprites and level backgrounds must be non-interlaced 8-bit indexed PNGs "
                    f"(bit_depth={bit_depth}, color_type={color_type})"
                )
        elif color_type not in {2, 3, 6}:
            raise ValueError(f"{path}: unsupported PNG color type {color_type}")
        checked.append(relative)
    return checked


def check_character_palettes(data_root: Path) -> None:
    """A model's indexed frames must use one palette; OpenBOR uses a model palette base."""
    for sprite_root in sorted(data_root.glob("chars/*/sprites")):
        images = sorted(sprite_root.rglob("*.png"))
        if not images:
            continue
        expected: bytes | None = None
        expected_path: Path | None = None
        for path in images:
            with Image.open(path) as image:
                if image.mode != "P" or image.info.get("transparency") != 0:
                    raise ValueError(f"{path}: character frame must be indexed with palette index 0 transparent")
                palette = bytes(image.getpalette() or [])
            if expected is None:
                expected, expected_path = palette, path
            elif palette != expected:
                raise ValueError(f"{path}: palette differs from model palette base {expected_path}")


def check_video_config(data_root: Path) -> None:
    path = data_root / "video.txt"
    if not path.is_file():
        raise ValueError(f"{path}: required OpenBOR video configuration is missing")
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="strict").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    video_lines = [line for line in lines if line.split(maxsplit=1)[0] == "video"]
    if len(video_lines) != 1 or not re.fullmatch(r"video\s+[0-9]+x[0-9]+", video_lines[0]):
        raise ValueError(f"{path}: expected exactly one parser-compatible 'video WIDTHxHEIGHT' directive")
    for line in lines:
        command = line.split(maxsplit=1)[0]
        if command.startswith("a") and len(command) > 1 and command[1].isdigit():
            raise ValueError(f"{path}: unsupported resolution token '{command}'; use 'video WIDTHxHEIGHT'")


def check_text_directives(data_root: Path) -> list[str]:
    checked: list[str] = []
    for path in sorted(data_root.rglob("*.txt")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
            command = line.strip().split(maxsplit=1)[0] if line.strip() and not line.lstrip().startswith("#") else ""
            if command in REJECTED_DIRECTIVES:
                raise ValueError(f"{path}:{line_number}: unsupported OpenBOR directive '{command}'")
        checked.append(path.relative_to(data_root).as_posix())
    return checked


def resolve_case_stable_data_path(
    data_root: Path,
    raw_path: str,
    declaration_path: Path,
    line_number: int,
) -> Path:
    """Resolve an OpenBOR data/... path while enforcing exact component case."""
    if not raw_path.isascii() or "\\" in raw_path:
        raise ValueError(
            f"{declaration_path}:{line_number}: asset path must be ASCII and use forward slashes: {raw_path!r}"
        )
    components = raw_path.split("/")
    if not components or components[0] != "data" or any(part in {"", ".", ".."} for part in components):
        raise ValueError(
            f"{declaration_path}:{line_number}: asset path must be a normalized, case-stable data/... path: {raw_path!r}"
        )

    current = data_root
    for component in components[1:]:
        if not current.is_dir():
            raise ValueError(f"{declaration_path}:{line_number}: asset path does not exist: {raw_path}")
        entries = list(current.iterdir())
        exact = next((entry for entry in entries if entry.name == component), None)
        if exact is None:
            case_matches = sorted(entry.name for entry in entries if entry.name.casefold() == component.casefold())
            if case_matches:
                raise ValueError(
                    f"{declaration_path}:{line_number}: asset path case mismatch in {raw_path!r}; "
                    f"filesystem spelling is {case_matches[0]!r}"
                )
            raise ValueError(f"{declaration_path}:{line_number}: asset path does not exist: {raw_path}")
        current = exact

    if not current.is_file():
        raise ValueError(f"{declaration_path}:{line_number}: asset path is not a file: {raw_path}")
    return current


def check_stage_indexed_image(path: Path, *, require_transparency: bool) -> bytes:
    """Validate the pinned underpass image contract and return rendered pixels."""
    width, height, bit_depth, color_type, compression, filtering, interlace = png_header(path)
    if (
        (width, height) != STAGE_IMAGE_SIZE
        or bit_depth != 8
        or color_type != 3
        or compression != 0
        or filtering != 0
        or interlace != 0
    ):
        raise ValueError(
            f"{path}: underpass stage image must be a non-interlaced 8-bit indexed 640x360 PNG "
            f"(size={width}x{height}, bit_depth={bit_depth}, color_type={color_type}, interlace={interlace})"
        )
    with Image.open(path) as image:
        if image.mode != "P":
            raise ValueError(f"{path}: underpass stage image must use Pillow indexed mode P")
        if require_transparency and image.info.get("transparency") != 0:
            raise ValueError(f"{path}: underpass panel must reserve palette index 0 for transparency")
        return image.convert("RGBA").tobytes()


def check_i8_underpass_stage(data_root: Path) -> None:
    """Validate the active Build 7949 panel/layer contract when the stage is present."""
    stage_path = data_root.joinpath(*I8_UNDERPASS_LEVEL.parts)
    if not stage_path.is_file():
        return

    directives: list[tuple[int, str, list[str]]] = []
    for line_number, line in enumerate(stage_path.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
        content = line.split("#", 1)[0].strip()
        if not content:
            continue
        tokens = content.split()
        directives.append((line_number, tokens[0].lower(), tokens[1:]))

    panel_declarations = [(line_number, args) for line_number, command, args in directives if command == "panel"]
    if not panel_declarations:
        raise ValueError(f"{stage_path}: active i8_underpass stage must declare at least one 640x360 panel")
    if len(panel_declarations) > 26:
        raise ValueError(f"{stage_path}: Build 7949 panel definitions are limited to a-z (26 panels)")

    panel_digests: dict[bytes, Path] = {}
    for line_number, args in panel_declarations:
        if not args:
            raise ValueError(f"{stage_path}:{line_number}: panel directive is missing its asset path")
        panel_path = resolve_case_stable_data_path(data_root, args[0], stage_path, line_number)
        pixels = check_stage_indexed_image(panel_path, require_transparency=True)
        digest = hashlib.sha256(pixels).digest()
        if digest in panel_digests:
            raise ValueError(
                f"{stage_path}:{line_number}: panel {panel_path} duplicates exact rendered pixels from "
                f"{panel_digests[digest]}"
            )
        panel_digests[digest] = panel_path

    order_declarations = [(line_number, args) for line_number, command, args in directives if command == "order"]
    if not order_declarations:
        raise ValueError(f"{stage_path}: active i8_underpass stage must declare panel order")
    for line_number, args in order_declarations:
        if not args:
            raise ValueError(f"{stage_path}:{line_number}: order directive is missing its panel sequence")
        for symbol in args[0]:
            if not symbol.isascii() or not symbol.isalpha():
                raise ValueError(f"{stage_path}:{line_number}: invalid panel order symbol {symbol!r}")
            panel_index = ord(symbol.lower()) - ord("a")
            if panel_index < 0 or panel_index >= len(panel_declarations):
                raise ValueError(
                    f"{stage_path}:{line_number}: panel order references undefined panel {symbol!r}; "
                    f"only a-{chr(ord('a') + len(panel_declarations) - 1)} are defined"
                )

    background_declarations = [
        (line_number, args) for line_number, command, args in directives if command == "background"
    ]
    if len(background_declarations) != 1:
        raise ValueError(f"{stage_path}: active i8_underpass stage must declare exactly one 640x360 background")
    background_line, background_args = background_declarations[0]
    if not background_args:
        raise ValueError(f"{stage_path}:{background_line}: background directive is missing its asset path")
    background_path = resolve_case_stable_data_path(
        data_root, background_args[0], stage_path, background_line
    )
    check_stage_indexed_image(background_path, require_transparency=False)

    for line_number, command, args in directives:
        maximum = LAYER_MAX_ARGUMENTS.get(command)
        if maximum is None:
            continue
        if not args:
            raise ValueError(f"{stage_path}:{line_number}: {command} directive is missing its asset path")
        if len(args) > maximum:
            raise ValueError(
                f"{stage_path}:{line_number}: {command} has {len(args)} arguments after the directive; "
                f"Build 7949 accepts at most {maximum}"
            )
        resolve_case_stable_data_path(data_root, args[0], stage_path, line_number)

    detached_foliage = [
        (line_number, args[0])
        for line_number, command, args in directives
        if command == "fglayer" and args and "foliage" in args[0].casefold()
    ]
    if detached_foliage:
        line_number, asset = detached_foliage[0]
        raise ValueError(
            f"{stage_path}:{line_number}: underpass foliage must be rooted animated scenery behind players, "
            f"not a distorted foreground layer ({asset})"
        )

    foliage_model = data_root / "levels/i8_underpass/underpass_foliage.txt"
    if not foliage_model.is_file():
        raise ValueError(f"{foliage_model}: rooted underpass foliage model is missing")
    foliage_text = foliage_model.read_text(encoding="utf-8", errors="strict")
    frame_refs = re.findall(r"(?m)^\s*frame\s+(data/levels/i8_underpass/scenery/\S+\.png)\s*$", foliage_text)
    if len(frame_refs) != 4 or len(set(frame_refs)) != 3:
        raise ValueError(
            f"{foliage_model}: expected a four-cel 1-2-3-2 sway using exactly three unique pixel drawings"
        )
    expected_palette: bytes | None = None
    rendered_frames: set[bytes] = set()
    for frame_ref in sorted(set(frame_refs)):
        frame_path = resolve_case_stable_data_path(data_root, frame_ref, foliage_model, 1)
        width, height, bit_depth, color_type, compression, filtering, interlace = png_header(frame_path)
        if (
            (width, height) != UNDERPASS_FOLIAGE_FRAME_SIZE
            or bit_depth != 8
            or color_type != 3
            or compression != 0
            or filtering != 0
            or interlace != 0
        ):
            raise ValueError(
                f"{frame_path}: rooted foliage frame must be non-interlaced indexed "
                f"{UNDERPASS_FOLIAGE_FRAME_SIZE[0]}x{UNDERPASS_FOLIAGE_FRAME_SIZE[1]}"
            )
        with Image.open(frame_path) as frame_image:
            if frame_image.mode != "P" or frame_image.info.get("transparency") != 0:
                raise ValueError(f"{frame_path}: foliage frame must reserve palette index 0 for transparency")
            palette = bytes(frame_image.getpalette() or [])
            rendered_frames.add(hashlib.sha256(frame_image.convert("RGBA").tobytes()).digest())
        if expected_palette is None:
            expected_palette = palette
        elif palette != expected_palette:
            raise ValueError(f"{frame_path}: foliage frames must share one identical indexed palette")
    if len(rendered_frames) != 3:
        raise ValueError(f"{foliage_model}: foliage sway must contain three unique rendered drawings")

    model_registry = (data_root / "models.txt").read_text(encoding="utf-8", errors="strict")
    expected_load = "load UnderpassFoliage data/levels/i8_underpass/underpass_foliage.txt"
    if expected_load not in model_registry:
        raise ValueError(f"{data_root / 'models.txt'}: missing rooted foliage model load")
    spawn_count = sum(1 for _, command, args in directives if command == "spawn" and args == ["UnderpassFoliage"])
    if spawn_count < 4:
        raise ValueError(f"{stage_path}: expected multiple localized UnderpassFoliage scenery spawns")


def check_animation_capacity(data_root: Path) -> None:
    models = data_root / "models.txt"
    model_text = models.read_text(encoding="utf-8", errors="strict")
    match = re.search(r"(?m)^\s*maxfreespecials\s+(\d+)\s*$", model_text)
    if match and int(match.group(1)) > 8:
        raise ValueError(f"{models}: Build 7949 supports at most eight safe native freespecial slots")
    unsupported = re.compile(r"ANI_FREESPECIAL(?:9|[1-9][0-9]+)")
    for path in sorted(data_root.rglob("*.c")):
        hit = unsupported.search(path.read_text(encoding="utf-8", errors="strict"))
        if hit:
            raise ValueError(f"{path}: unsupported Build 7949 animation constant {hit.group(0)}")


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("openbor/data"))
    parser.add_argument("--pak", type=Path)
    args = parser.parse_args()
    data_root = args.data.resolve()
    pngs = check_pngs(data_root)
    check_character_palettes(data_root)
    check_video_config(data_root)
    check_animation_capacity(data_root)
    check_i8_underpass_stage(data_root)
    text_files = check_text_directives(data_root)
    entries = check_pack(data_root, args.pak.resolve()) if args.pak else None
    print({"status": "pass", "pngs": len(pngs), "text_files": len(text_files), "pak_entries": entries})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
