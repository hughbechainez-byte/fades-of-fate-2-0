"""Fail-fast OpenBOR asset and package compatibility checks."""

from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path

from PIL import Image


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
REJECTED_DIRECTIVES = {"shadow_coords"}


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
    text_files = check_text_directives(data_root)
    entries = check_pack(data_root, args.pak.resolve()) if args.pak else None
    print({"status": "pass", "pngs": len(pngs), "text_files": len(text_files), "pak_entries": entries})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
