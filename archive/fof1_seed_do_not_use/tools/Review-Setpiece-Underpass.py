#!/usr/bin/env python3
"""Ground-up underpass setpiece life review (no characters, no FoF1 cars).

Composites living ambient (birds, mist, foliage sway, restrained glow) onto the
approved 2.0 underpass *target still* — not the legacy FoF1 location-lock plate
and not previous-game vehicle models.

This is the review package for setpiece quality before standardization.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
from typing import Sequence

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import LOGICAL_SIZE  # noqa: E402

DEFAULT_DESKTOP = Path("/mnt/c/Users/blowb/Desktop/Fades of Fate 2.0 - Review Photos")
# Prefer the approved look-dev target (same aesthetic as photos 01/02).
DEFAULT_PLATE_CANDIDATES = (
    DEFAULT_DESKTOP / "01_underpass_environment_only.png",
    DEFAULT_DESKTOP / "target_renders" / "ch1_l2_i8_underpass_target.png",
    PROJECT_ROOT / "docs" / "visual_direction" / "target_renders" / "ch1_l2_i8_underpass_target.png",
    PROJECT_ROOT
    / "art_source"
    / "chapter1_location_locked"
    / "source_panels"
    / "l2_p4_i8_underpass_v3_source.png",
)
SETPIECE_SUBDIR = "setpiece_review_underpass_groundup"


def _i(value: float) -> int:
    return int(round(value))


def _resolve_plate(explicit: Path | None) -> Path:
    if explicit is not None and explicit.is_file():
        return explicit
    for candidate in DEFAULT_PLATE_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "No underpass plate found. Expected one of:\n  "
        + "\n  ".join(str(path) for path in DEFAULT_PLATE_CANDIDATES)
    )


def _load_plate(path: Path) -> pygame.Surface:
    image = pygame.image.load(str(path)).convert()
    if image.get_size() != LOGICAL_SIZE:
        # Nearest-neighbor only — gameplay pixel contract.
        image = pygame.transform.scale(image, LOGICAL_SIZE)
    return image


def _draw_birds(surface: pygame.Surface, tick: int, seed: int = 71) -> None:
    width = surface.get_width()
    count = 7
    period = width + 120
    for index in range(count):
        travel = _i(tick * (0.55 if index % 2 == 0 else 0.38)) * (1 if index % 3 else -1)
        x = -60 + ((seed * 19 + index * 97 + travel) % period)
        y = 78 + (index * 11 + seed) % 36
        wing = 2 + ((tick // 4 + index) % 2) * 3
        color = (32, 28, 36, 200)
        pygame.draw.line(surface, color, (x - 6, y + wing), (x, y), 2)
        pygame.draw.line(surface, color, (x, y), (x + 6, y + wing), 2)
        pygame.draw.rect(surface, (40, 36, 44, 170), (x - 1, y - 1, 2, 2))


def _draw_mist(surface: pygame.Surface, tick: int, seed: int = 43) -> None:
    width, height = surface.get_size()
    for band, base_y, count, speed in (
        (0, 150, 10, 0.14),
        (1, 188, 8, 0.10),
        (2, 250, 6, 0.12),
    ):
        span = width + 80
        for index in range(count):
            drift = _i(tick * speed) + seed * 7 + band * 31 + index * 53
            x = -40 + (drift % span)
            y = base_y + (seed * 3 + index * 17 + tick // 6) % 28
            size = 2 + (index + seed) % 3
            mist = (150, 168, 172, 18 + size * 5)
            pygame.draw.ellipse(surface, mist, (x, y, 18 + size * 6, 4 + size))
            pygame.draw.rect(surface, (180, 190, 188, 14 + size * 3), (x + 4, y + 2, 12 + size * 4, 2))
    del height


def _draw_foliage(surface: pygame.Surface, tick: int, seed: int = 101) -> None:
    # Grounded scrub along the fence line / lower mid band of the target still.
    anchors = (70, 140, 210, 300, 390, 470, 540, 600)
    phase = tick // 5
    for index, base_x in enumerate(anchors):
        sway = ((phase + index * 3 + seed) % 7) - 3
        base_y = 268 + (index % 3) * 3
        top = base_y - (16 + (index * 4 + seed) % 12)
        pygame.draw.line(surface, (46, 50, 40, 190), (base_x, base_y), (base_x + sway, top), 2)
        canopy = (
            (base_x + sway - 8, top + 3),
            (base_x + sway - 1, top - 6),
            (base_x + sway + 7, top - 1),
            (base_x + sway + 5, top + 7),
            (base_x + sway - 5, top + 8),
        )
        body = (58, 78, 54, 150) if index % 2 else (70, 88, 58, 145)
        pygame.draw.polygon(surface, body, canopy)


def _draw_soft_glow(surface: pygame.Surface, tick: int, seed: int = 19) -> None:
    """Restrained practical language matching the target still — no candy neon."""

    width, height = surface.get_size()
    pulse = (tick // 8 + seed) % 3
    # Cool concrete deck wash under the overpass mass.
    pygame.draw.rect(surface, (60, 72, 84, 10 + pulse), (0, 120, width, 70))
    # Sparse warm practical spots under the deck (sodium, not magenta).
    for index, x in enumerate((120, 240, 360, 480)):
        lamp = (255, 190, 120, 16 + pulse)
        pygame.draw.ellipse(surface, lamp, (x - 28, 200, 56, 18))
        pygame.draw.rect(surface, (255, 196, 128, 40), (x - 4, 148, 8, 2))
    # Quiet warm edge where portal sky meets concrete.
    pygame.draw.rect(surface, (255, 150, 100, 10 + pulse), (0, 132, 3, 90))
    pygame.draw.rect(surface, (255, 150, 100, 10 + pulse), (width - 3, 132, 3, 90))
    # Subtle warm ground catches only.
    for index in range(6):
        x = 40 + ((seed * 17 + index * 89 + tick // 3) % (width - 80))
        y = 310 + (index * 7 + seed) % 20
        pygame.draw.ellipse(surface, (200, 145, 95, 28), (x, y, 9 + index % 3, 2))
    del height


def _draw_paper_dust(surface: pygame.Surface, tick: int, seed: int = 47) -> None:
    width = surface.get_width()
    for index in range(5):
        drift = _i(tick * 0.25) + seed * 5 + index * 61
        x = -20 + (drift % (width + 40))
        y = 280 + (seed * 3 + index * 19 + tick // 5) % 40
        color = (210, 198, 170, 120) if index % 2 else (160, 150, 140, 100)
        pygame.draw.polygon(
            surface,
            color,
            [(x, y), (x + 4, y - 1), (x + 5, y + 3), (x + 1, y + 4)],
        )


def compose_living_frame(plate: pygame.Surface, tick: int) -> pygame.Surface:
    """Plate + ambient overlay only. No characters, no vehicle assets."""

    frame = plate.copy()
    overlay = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
    _draw_birds(overlay, tick)
    _draw_mist(overlay, tick)
    _draw_foliage(overlay, tick)
    _draw_soft_glow(overlay, tick)
    _draw_paper_dust(overlay, tick)
    frame.blit(overlay, (0, 0))
    return frame


def _contact_sheet(frames: Sequence[pygame.Surface], columns: int = 4) -> pygame.Surface:
    width, height = frames[0].get_size()
    columns = max(1, min(columns, len(frames)))
    rows = (len(frames) + columns - 1) // columns
    sheet = pygame.Surface((width * columns, height * rows))
    sheet.fill((16, 18, 24))
    for index, frame in enumerate(frames):
        col = index % columns
        row = index // columns
        sheet.blit(frame, (col * width, row * height))
        pygame.draw.rect(sheet, (48, 54, 66), (col * width, row * height, width, height), 1)
    return sheet


def _write(path: Path, surface: pygame.Surface) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--plate", type=Path, default=None, help="Override plate PNG")
    parser.add_argument("--desktop", type=Path, default=DEFAULT_DESKTOP)
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--no-desktop", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    os.chdir(project_root)

    pygame.init()
    pygame.display.set_mode((1, 1))

    plate_path = _resolve_plate(args.plate)
    plate = _load_plate(plate_path)

    local_dir = project_root / "build" / "setpiece_review" / "underpass_groundup"
    local_dir.mkdir(parents=True, exist_ok=True)
    desktop_dir: Path | None = None
    if not args.no_desktop and str(args.desktop).strip():
        desktop_dir = Path(args.desktop) / SETPIECE_SUBDIR
        desktop_dir.mkdir(parents=True, exist_ok=True)
        # Clean prior mismatched engine-only package names from root for clarity.
        review_root = Path(args.desktop)
        for stale in (
            "03_underpass_living_still.png",
            "04_underpass_living_mid.png",
            "05_underpass_living_contact_sheet.png",
            "06_underpass_early_vs_late.png",
            "07_underpass_deep_setpiece.png",
            "08_underpass_approach.png",
            "SETPIECE_REVIEW_INDEX.txt",
        ):
            stale_path = review_root / stale
            if stale_path.is_file():
                archive = review_root / "_archive_mismatched_fof1_engine_captures"
                archive.mkdir(exist_ok=True)
                stale_path.replace(archive / stale)

    frame_count = max(4, args.frames)
    ticks = [index * 6 for index in range(frame_count)]  # ~0.2s steps at 30Hz presentation
    frames: list[pygame.Surface] = []
    written: list[str] = []

    for index, tick in enumerate(ticks):
        frame = compose_living_frame(plate, tick)
        name = f"life_{index:02d}_tick{tick:03d}.png"
        _write(local_dir / name, frame)
        if desktop_dir is not None:
            _write(desktop_dir / name, frame)
        written.append(name)
        frames.append(frame)

    sheet = _contact_sheet(frames, columns=4)
    pair = pygame.Surface((LOGICAL_SIZE[0] * 2, LOGICAL_SIZE[1]))
    pair.blit(frames[0], (0, 0))
    pair.blit(frames[-1], (LOGICAL_SIZE[0], 0))
    pygame.draw.line(
        pair,
        (240, 210, 90),
        (LOGICAL_SIZE[0], 0),
        (LOGICAL_SIZE[0], LOGICAL_SIZE[1]),
        2,
    )

    for name, surface in (
        ("life_contact_sheet.png", sheet),
        ("life_early_vs_late.png", pair),
        ("plate_source_scaled.png", plate),
    ):
        _write(local_dir / name, surface)
        if desktop_dir is not None:
            _write(desktop_dir / name, surface)
        written.append(name)

    if desktop_dir is not None:
        root = desktop_dir.parent
        # Clear top-level aliases that match the approved target aesthetic + life.
        _write(root / "03_underpass_groundup_still.png", frames[0])
        _write(root / "04_underpass_groundup_mid.png", frames[len(frames) // 2])
        _write(root / "05_underpass_groundup_contact_sheet.png", sheet)
        _write(root / "06_underpass_groundup_early_vs_late.png", pair)
        # Keep lookdev targets clearly labeled.
        lookdev = root / "lookdev_targets_not_engine"
        lookdev.mkdir(exist_ok=True)
        for name in (
            "01_underpass_environment_only.png",
            "02_underpass_with_black_dave.png",
        ):
            src = root / name
            if src.is_file() and not (lookdev / name).exists():
                # Copy, leave originals for easy open too.
                _write(lookdev / name, pygame.image.load(str(src)))

        (desktop_dir / "README.txt").write_text(
            "\n".join(
                [
                    "Ground-up underpass setpiece life review",
                    "========================================",
                    "",
                    f"Plate source: {plate_path}",
                    "This package uses the 2.0 TARGET still (look-dev aesthetic),",
                    "NOT the legacy FoF1 location-lock plate.",
                    "",
                    "NO previous-game vehicle models.",
                    "NO characters / enemies.",
                    "Life layers: birds, mist, foliage sway, soft practical glow,",
                    "paper/dust. Colors are restrained (warm practicals + cool",
                    "concrete wash) — no magenta/cyan candy chips.",
                    "",
                    "Open on Desktop root:",
                    "  03_underpass_groundup_still.png",
                    "  04_underpass_groundup_mid.png",
                    "  05_underpass_groundup_contact_sheet.png",
                    "  06_underpass_groundup_early_vs_late.png",
                    "",
                    "01/02 remain lookdev targets (static).",
                    "Mismatched FoF1 engine captures were moved to",
                    "  _archive_mismatched_fof1_engine_captures/",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (root / "SETPIECE_REVIEW_INDEX.txt").write_text(
            "\n".join(
                [
                    "Fades of Fate 2.0 — Underpass review index",
                    "==========================================",
                    "",
                    "LOOKDEV (static targets, not live engine):",
                    "  01_underpass_environment_only.png",
                    "  02_underpass_with_black_dave.png",
                    "",
                    "GROUND-UP LIVING REVIEW (target aesthetic + life, no FoF1 cars):",
                    "  03_underpass_groundup_still.png",
                    "  04_underpass_groundup_mid.png",
                    "  05_underpass_groundup_contact_sheet.png",
                    "  06_underpass_groundup_early_vs_late.png",
                    "  setpiece_review_underpass_groundup\\",
                    "",
                    "ARCHIVED (wrong look / legacy vehicles):",
                    "  _archive_mismatched_fof1_engine_captures\\",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    manifest = {
        "schema_version": 1,
        "review_id": "setpiece_underpass_groundup_living",
        "plate_source": str(plate_path),
        "logical_canvas": list(LOGICAL_SIZE),
        "characters": False,
        "enemies": False,
        "legacy_vehicle_models": False,
        "uses_fof1_location_lock_plate": False,
        "life_layers": [
            "birds",
            "mist",
            "foliage_sway",
            "soft_practical_glow",
            "paper_dust",
        ],
        "frames": written,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": (
            "Living setpiece review on the 2.0 target aesthetic. "
            "Approve/request edits before promoting as quality floor."
        ),
    }
    (local_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if desktop_dir is not None:
        (desktop_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "plate": str(plate_path),
                "local": str(local_dir),
                "desktop": str(desktop_dir) if desktop_dir else None,
                "frames": len(frames),
                "legacy_vehicles": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
