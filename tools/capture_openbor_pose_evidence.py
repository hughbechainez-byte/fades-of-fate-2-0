"""Capture and verify all 460 authored poses from packaged OpenBOR Build 7949.

The in-game showcase owns animation selection.  This external tool observes the
fixed updatedscript HUD barcode and prefers the pinned runtime's native F12 PNG.
If the official executable does not produce a valid native screenshot during
the baseline probe, the tool captures either the exact 640x360 Windows client
or the observed 960x540 client normalized to 640x360 with nearest-neighbor.
Fallback evidence is never described as a native OpenBOR screenshot.

Required ``entity_tech_demo.c`` contract (native 640x360 coordinates):

* updatedscript draws a black quiet strip at ``openborvariant("hud_z") + 100``;
  the 6x8 cells are start at x=8, twelve little-endian payload bits at
  x=16+8*i, even parity at x=112, and end at x=120, all at y=28;
* index 4095 is an entity-free baseline; indexes 0..459 are the schedule emitted
  by :func:`build_schedule` (Dave 0..219, homeless 220..339, police 340..459);
* updatedscript also draws the literal pose ID at ``(8, 8)``;
* exactly one actor is visible at screen root ``(320, 300)``, authored direction
  1, with model offset/root ``(96, 156)``.  Other actors and effects are outside
  the 192x160 verification ROI.

The marker must be queued at HUD+100.  Entity sprites may be queued earlier:
OpenBOR sorts the shared sprite queue by z before the framebuffer is captured,
so the marker remains visible while the source sprite can still be compared to
the entity-free baseline.  The marker rectangle is outside the body ROI.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import inspect
import json
import math
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageGrab


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SIZE = (640, 360)
OBSERVED_CLIENT_SIZE = (960, 540)
EXPECTED_TOTAL = 460
ENTITY_COUNTS = {"black_dave": 220, "homeless_man": 120, "police_officer": 120}
ENTITY_ORDER = tuple(ENTITY_COUNTS)
MODEL_ROOT = (96, 156)
SCREEN_ROOT = (320, 300)
ROI = (SCREEN_ROOT[0] - MODEL_ROOT[0], SCREEN_ROOT[1] - MODEL_ROOT[1], 192, 160)
DIRECTION = 1
BARCODE_Y = 28
BARCODE_START_X = 8
BARCODE_PAYLOAD_X = 16
BARCODE_PARITY_X = 112
BARCODE_END_X = 120
BARCODE_CELL = (6, 8)
BARCODE_PITCH = 8
BARCODE_PAYLOAD_BITS = 12
BARCODE_TOTAL_CELLS = 15
BARCODE_STRIP = (4, 4, 132, 40)
BASELINE_INDEX = 4095
BARCODE_Z_OFFSET = 100
DAVE_HOLD_TICKS = 12
ENEMY_HOLD_TICKS = 40
RGB_EXACT_MIN = 0.995
SILHOUETTE_IOU_MIN = 0.98
BEST_MARGIN_MIN = 0.01
ALIGN_RADIUS = 2
GROUND_SHADOW_HALF_HEIGHT = 5
METHOD_NATIVE_F12 = "openbor_native_f12"
METHOD_CLIENT_EXACT = "windows_client_capture_exact"
METHOD_CLIENT_NORMALIZED = "windows_client_capture_normalized"
NORMALIZATION_NONE = "none"
NORMALIZATION_NEAREST = "nearest_neighbor"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(f"evidence artifact must stay under repository root: {resolved}") from exc


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"evidence path must be repository-relative: {value}")
    resolved = (ROOT / path).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"evidence path escapes repository: {value}") from exc
    return resolved


def palette_hash(image: Image.Image) -> str:
    palette = image.getpalette()
    if palette is None:
        raise ValueError("indexed source sprite has no palette")
    return sha256_bytes(bytes((palette + [0] * 768)[:768]))


def opaque_mask(image: Image.Image) -> Image.Image:
    if image.mode != "P" or image.info.get("transparency") != 0:
        raise ValueError("source pose must be indexed with transparency index 0")
    return image.point(lambda value: 255 if value != 0 else 0, mode="L")


def mask_hash(mask: Image.Image) -> str:
    return sha256_bytes(mask.size[0].to_bytes(2, "big") + mask.size[1].to_bytes(2, "big") + mask.tobytes())


def count_mask(mask: Image.Image) -> int:
    return mask.histogram()[255]


def encode_barcode(index: int) -> tuple[int, ...]:
    if not 0 <= index <= 0xFFF:
        raise ValueError(f"barcode index exceeds twelve-bit payload: {index}")
    payload = tuple((index >> bit) & 1 for bit in range(BARCODE_PAYLOAD_BITS))
    parity = sum(payload) & 1
    return (1, *payload, parity, 1)


def _barcode_x(cell: int) -> int:
    if cell == 0:
        return BARCODE_START_X
    if 1 <= cell <= BARCODE_PAYLOAD_BITS:
        return BARCODE_PAYLOAD_X + (cell - 1) * BARCODE_PITCH
    if cell == BARCODE_PAYLOAD_BITS + 1:
        return BARCODE_PARITY_X
    if cell == BARCODE_PAYLOAD_BITS + 2:
        return BARCODE_END_X
    raise ValueError(f"invalid barcode cell {cell}")


def _cell_luma(image: Image.Image, cell: int) -> float:
    x = _barcode_x(cell)
    y = BARCODE_Y
    inset_x, inset_y = 1, 2
    crop = image.convert("RGB").crop(
        (x + inset_x, y + inset_y, x + BARCODE_CELL[0] - inset_x, y + BARCODE_CELL[1] - inset_y)
    )
    pixels = list(crop.getdata())
    return sum((299 * r + 587 * g + 114 * b) / 1000 for r, g, b in pixels) / len(pixels)


def decode_barcode(image: Image.Image) -> dict:
    if image.size != EXPECTED_SIZE:
        raise ValueError(f"barcode image must be {EXPECTED_SIZE}, got {image.size}")
    luma = [_cell_luma(image, cell) for cell in range(BARCODE_TOTAL_CELLS)]
    bits = tuple(1 if value >= 128 else 0 for value in luma)
    if bits[0] != 1 or bits[-1] != 1:
        raise ValueError(f"barcode sentinel failure: {bits}")
    payload = bits[1 : 1 + BARCODE_PAYLOAD_BITS]
    parity = sum(payload) & 1
    if bits[-2] != parity:
        raise ValueError(f"barcode parity failure: {bits}")
    index = sum(value << bit for bit, value in enumerate(payload))
    return {"index": index, "bits": list(bits), "luma": [round(value, 3) for value in luma], "parity": parity}


@dataclass(frozen=True)
class PoseTemplate:
    global_index: int
    entity: str
    pose_id: str
    group: str
    source_path: str
    generated_path: str
    sprite_sha256: str
    palette_sha256: str
    opaque_mask_sha256: str
    opaque_pixels: int
    model_animation: str
    animation_constant: str
    frame_index: int
    hold_ticks: int

    def source_image(self) -> Image.Image:
        return _cached_source_image(self.source_path)


@dataclass(frozen=True)
class CapturedPose:
    template: PoseTemplate
    screenshot_path: Path
    decoded: dict
    geometry: dict
    stable_polls: int
    captured_at_utc: str


@lru_cache(maxsize=None)
def _cached_source_image(source_path: str) -> Image.Image:
    with Image.open(resolve_repo_path(source_path)) as image:
        return image.copy()


def _source_pose_records(entity: str) -> tuple[dict, dict[str, dict]]:
    path = ROOT / "content" / "characters" / entity / "sprites" / "pose_manifest.json"
    manifest = load_json(path)
    poses = manifest.get("poses", [])
    expected = ENTITY_COUNTS[entity]
    if len(poses) != expected or len({pose.get("id") for pose in poses}) != expected:
        raise ValueError(f"{path}: expected {expected} unique pose records")
    return manifest, {pose["id"]: pose for pose in poses}


def _runtime_mapping(entity: str, poses: dict[str, dict]) -> dict[str, tuple[str, str, int, int]]:
    if entity == "black_dave":
        schedule_path = ROOT / "openbor/data/chars/black_dave/black_dave_pose_qa_schedule.json"
        schedule = load_json(schedule_path)
        if int(schedule.get("request_count", -1)) != 220:
            raise ValueError(f"{schedule_path}: expected 220 requests")
        result = {}
        requests = sorted(schedule.get("requests", []), key=lambda item: int(item["request"]))
        if [int(item["request"]) for item in requests] != list(range(220)):
            raise ValueError(f"{schedule_path}: request indexes must be exactly 0..219")
        for request in requests:
            pose_id = request["pose_id"]
            if pose_id in result:
                raise ValueError(f"{schedule_path}: duplicate pose {pose_id}")
            result[pose_id] = (
                request["animation"],
                request["animation_constant"],
                int(request["frame"]),
                int(request.get("hold_ticks", schedule.get("hold_ticks_per_pose", 0))),
            )
            if result[pose_id][3] != DAVE_HOLD_TICKS:
                raise ValueError(f"{schedule_path}: {pose_id} hold must be exactly {DAVE_HOLD_TICKS} ticks")
        return result
    result = {}
    for pose_id, pose in poses.items():
        runtime = pose.get("runtime", {})
        animation = runtime.get("model_animation")
        frame = runtime.get("frame_index")
        if animation is None or frame is None:
            raise ValueError(f"{entity}:{pose_id}: runtime mapping is incomplete")
        result[pose_id] = (str(animation), f"ANI_{str(animation).upper()}", int(frame), ENEMY_HOLD_TICKS)
    return result


def build_schedule() -> list[PoseTemplate]:
    templates: list[PoseTemplate] = []
    for entity in ENTITY_ORDER:
        manifest, by_id = _source_pose_records(entity)
        mapping = _runtime_mapping(entity, by_id)
        if entity == "black_dave":
            schedule_path = ROOT / "openbor/data/chars/black_dave/black_dave_pose_qa_schedule.json"
            requests = sorted(load_json(schedule_path)["requests"], key=lambda item: int(item["request"]))
            ordered = [by_id[request["pose_id"]] for request in requests]
        else:
            ordered = manifest["poses"]
        if set(mapping) != set(by_id):
            missing = sorted(set(by_id) - set(mapping))
            extra = sorted(set(mapping) - set(by_id))
            raise ValueError(f"{entity}: mapping mismatch missing={missing[:4]} extra={extra[:4]}")
        for pose in ordered:
            pose_id = pose["id"]
            animation, constant, frame, hold_ticks = mapping[pose_id]
            expected_hold = DAVE_HOLD_TICKS if entity == "black_dave" else ENEMY_HOLD_TICKS
            if hold_ticks != expected_hold:
                raise ValueError(f"{entity}:{pose_id}: showcase hold {hold_ticks} != {expected_hold}")
            source = resolve_repo_path(pose["path"])
            if sha256(source) != pose.get("sha256"):
                raise ValueError(f"{entity}:{pose_id}: source hash drift")
            image = Image.open(source)
            mask = opaque_mask(image)
            templates.append(
                PoseTemplate(
                    global_index=len(templates),
                    entity=entity,
                    pose_id=pose_id,
                    group=pose["group"],
                    source_path=repo_path(source),
                    generated_path=pose["generated_path"],
                    sprite_sha256=pose["sha256"],
                    palette_sha256=palette_hash(image),
                    opaque_mask_sha256=mask_hash(mask),
                    opaque_pixels=count_mask(mask),
                    model_animation=animation,
                    animation_constant=constant,
                    frame_index=frame,
                    hold_ticks=hold_ticks,
                )
            )
    if len(templates) != EXPECTED_TOTAL or len({item.pose_id for item in templates}) != EXPECTED_TOTAL:
        raise ValueError(f"combined schedule must contain exactly {EXPECTED_TOTAL} unique poses")
    overlay_path = ROOT / "openbor/data/scripts/entity_pose_overlay.c"
    overlay_text = overlay_path.read_text(encoding="utf-8")
    labels = {
        int(index): pose_id
        for index, pose_id in re.findall(r'if\(index == (\d+)\) drawstring\(8, 8, 0, "\d+ ([^"]+)"', overlay_text)
    }
    expected_labels = {template.global_index: template.pose_id for template in templates}
    if labels != expected_labels:
        first = next((index for index in range(EXPECTED_TOTAL) if labels.get(index) != expected_labels[index]), None)
        raise ValueError(f"{overlay_path}: HUD pose labels do not match capture schedule at index {first}")
    return templates


def _crop_at(image: Image.Image, dx: int, dy: int) -> Image.Image:
    left, top, width, height = ROI
    return image.convert("RGB").crop((left + dx, top + dy, left + dx + width, top + dy + height))


def rgb_exact_score(capture: Image.Image, template: PoseTemplate, dx: int, dy: int) -> float:
    source = template.source_image()
    source_rgb = source.convert("RGB")
    mask = opaque_mask(source)
    observed = _crop_at(capture, dx, dy)
    difference = ImageChops.difference(observed, source_rgb)
    channels = difference.split()
    maximum = ImageChops.lighter(channels[0], ImageChops.lighter(channels[1], channels[2]))
    mismatch = maximum.point(lambda value: 255 if value > 1 else 0, mode="L")
    mismatch = ImageChops.multiply(mismatch, mask)
    return 1.0 - count_mask(mismatch) / template.opaque_pixels


def silhouette_iou(capture: Image.Image, baseline: Image.Image, template: PoseTemplate, dx: int, dy: int) -> float:
    observed = _crop_at(capture, dx, dy)
    clean = _crop_at(baseline, dx, dy)
    difference = ImageChops.difference(observed, clean)
    channels = difference.split()
    maximum = ImageChops.lighter(channels[0], ImageChops.lighter(channels[1], channels[2]))
    visible = maximum.point(lambda value: 255 if value > 2 else 0, mode="L")
    # Native shadows can vary slightly.  Ignore them only for silhouette IoU;
    # opaque sprite pixels in this band still participate in RGB verification.
    root_y = MODEL_ROOT[1] - dy
    draw = ImageDraw.Draw(visible)
    draw.rectangle((0, root_y - GROUND_SHADOW_HALF_HEIGHT, visible.width, root_y + GROUND_SHADOW_HALF_HEIGHT), fill=0)
    expected = opaque_mask(template.source_image())
    draw = ImageDraw.Draw(expected)
    draw.rectangle((0, root_y - GROUND_SHADOW_HALF_HEIGHT, expected.width, root_y + GROUND_SHADOW_HALF_HEIGHT), fill=0)
    intersection = count_mask(ImageChops.multiply(visible, expected))
    union = count_mask(ImageChops.lighter(visible, expected))
    return intersection / union if union else 1.0


def analyze_capture(
    capture: Image.Image,
    baseline: Image.Image,
    expected: PoseTemplate,
    candidates: Iterable[PoseTemplate],
) -> dict:
    if capture.size != EXPECTED_SIZE or baseline.size != EXPECTED_SIZE:
        raise ValueError("capture and baseline must be native 640x360 images")
    alignments = []
    for dy in range(-ALIGN_RADIUS, ALIGN_RADIUS + 1):
        for dx in range(-ALIGN_RADIUS, ALIGN_RADIUS + 1):
            alignments.append((rgb_exact_score(capture, expected, dx, dy), dx, dy))
    exact, dx, dy = max(alignments)
    candidates = list(candidates)
    scoped = [candidate for candidate in candidates if candidate.entity == expected.entity and candidate.group == expected.group]
    if len(scoped) < 2:
        scoped.extend(candidate for candidate in candidates if candidate.pose_id != expected.pose_id and candidate not in scoped)
        scoped = scoped[:2]
    rankings = sorted(
        ((rgb_exact_score(capture, candidate, dx, dy), candidate.pose_id) for candidate in scoped),
        reverse=True,
    )
    best_score, best_id = rankings[0]
    second_score, second_id = rankings[1]
    silhouette = silhouette_iou(capture, baseline, expected, dx, dy)
    margin = best_score - second_score
    failures = []
    if best_id != expected.pose_id:
        failures.append(f"best candidate {best_id} != expected {expected.pose_id}")
    if exact < RGB_EXACT_MIN:
        failures.append(f"rgb_exact {exact:.6f} < {RGB_EXACT_MIN}")
    if silhouette < SILHOUETTE_IOU_MIN:
        failures.append(f"silhouette_iou {silhouette:.6f} < {SILHOUETTE_IOU_MIN}")
    if margin < BEST_MARGIN_MIN:
        failures.append(f"best_margin {margin:.6f} < {BEST_MARGIN_MIN}")
    return {
        "alignment": [dx, dy],
        "rgb_exact": round(exact, 9),
        "silhouette_iou": round(silhouette, 9),
        "best_candidate": best_id,
        "best_score": round(best_score, 9),
        "second_candidate": second_id,
        "second_score": round(second_score, 9),
        "best_margin": round(margin, 9),
        "status": "pass" if not failures else "fail",
        "failures": failures,
    }


def draw_synthetic_barcode(image: Image.Image, index: int) -> None:
    draw = ImageDraw.Draw(image)
    x, y, width, height = BARCODE_STRIP
    draw.rectangle((x, y, x + width - 1, y + height - 1), fill=(0, 0, 0))
    for bit, value in enumerate(encode_barcode(index)):
        color = (255, 255, 255) if value else (0, 0, 0)
        x = _barcode_x(bit)
        y = BARCODE_Y
        draw.rectangle((x, y, x + BARCODE_CELL[0] - 1, y + BARCODE_CELL[1] - 1), fill=color)


def _find_window(pid: int, timeout: float) -> int:
    if sys.platform != "win32":
        raise RuntimeError("live capture requires Windows")
    user32 = ctypes.windll.user32
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        windows: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        @callback_type
        def callback(hwnd: int, _lparam: int) -> bool:
            window_pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value == pid and user32.IsWindowVisible(hwnd):
                windows.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)
        if windows:
            return windows[0]
        time.sleep(0.05)
    raise TimeoutError(f"OpenBOR window for PID {pid} did not appear")


class POINT(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


class RECT(ctypes.Structure):
    _fields_ = (("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long))


def _configure_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def _position_capture_window(hwnd: int) -> dict:
    """Place the verified SDL window above desktop UI at the QA client size."""
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    client = RECT()
    window = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        raise ctypes.WinError()
    if not user32.GetWindowRect(hwnd, ctypes.byref(window)):
        raise ctypes.WinError()
    client_width = client.right - client.left
    client_height = client.bottom - client.top
    frame_width = (window.right - window.left) - client_width
    frame_height = (window.bottom - window.top) - client_height
    target_client_size = (client_width, client_height)
    if target_client_size not in (EXPECTED_SIZE, OBSERVED_CLIENT_SIZE):
        raise ValueError(
            f"OpenBOR capture client must begin at {EXPECTED_SIZE} or {OBSERVED_CLIENT_SIZE}, got {target_client_size}"
        )
    outer_width = target_client_size[0] + frame_width
    outer_height = target_client_size[1] + frame_height
    work_area = RECT()
    spi_getworkarea = 0x0030
    if not user32.SystemParametersInfoW(spi_getworkarea, 0, ctypes.byref(work_area), 0):
        raise ctypes.WinError()
    x = max(work_area.left, work_area.right - outer_width)
    y = max(work_area.top, work_area.bottom - outer_height)
    hwnd_topmost = ctypes.c_void_p(-1)
    swp_showwindow = 0x0040
    if not user32.SetWindowPos(hwnd, hwnd_topmost, x, y, outer_width, outer_height, swp_showwindow):
        raise ctypes.WinError()
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.25)
    if user32.IsIconic(hwnd):
        raise ValueError("OpenBOR window remained minimized after capture placement")
    verified = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(verified)):
        raise ctypes.WinError()
    verified_size = (verified.right - verified.left, verified.bottom - verified.top)
    if verified_size != target_client_size:
        raise ValueError(
            f"OpenBOR capture client changed from {target_client_size} to {verified_size} during placement"
        )
    return {
        "capture_window_position": [x, y],
        "capture_window_client_size": list(verified_size),
        "capture_window_topmost": True,
        "capture_window_foreground": bool(user32.GetForegroundWindow() == hwnd),
    }


def _grab_client_raw(hwnd: int) -> Image.Image:
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        raise ValueError("OpenBOR window is minimized; client evidence would be invalid")
    user32.SetForegroundWindow(hwnd)
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    origin = POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise ctypes.WinError()
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise ValueError(f"OpenBOR client has invalid dimensions {(width, height)}")
    return ImageGrab.grab((origin.x, origin.y, origin.x + width, origin.y + height), all_screens=True).convert("RGB")


def normalize_client_capture(grabbed: Image.Image) -> tuple[Image.Image, dict]:
    """Normalize only the two source geometries covered by the evidence contract."""
    source_size = grabbed.size
    if source_size == EXPECTED_SIZE:
        return grabbed.convert("RGB"), {
            "source_size": list(source_size),
            "observed_client_size": list(source_size),
            "normalization": NORMALIZATION_NONE,
        }
    if source_size != OBSERVED_CLIENT_SIZE:
        raise ValueError(
            f"OpenBOR client must be {EXPECTED_SIZE} or observed {OBSERVED_CLIENT_SIZE}, got {source_size}"
        )
    return grabbed.convert("RGB").resize(EXPECTED_SIZE, Image.Resampling.NEAREST), {
        "source_size": list(source_size),
        "observed_client_size": list(source_size),
        "normalization": NORMALIZATION_NEAREST,
    }


def _grab_client(hwnd: int) -> tuple[Image.Image, dict]:
    return normalize_client_capture(_grab_client_raw(hwnd))


def _press_f12(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x7B, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(0x7B, 0, 2, 0)


def _next_marker_stability(stable: int, last: int | None, decoded_index: int | None, expected: int) -> int:
    if decoded_index != expected:
        return 0
    return stable + 1 if last == expected else 1


def _wait_for_marker(hwnd: int, expected: int, timeout: float, stable_polls: int) -> dict:
    deadline = time.monotonic() + timeout
    stable = 0
    last = None
    while time.monotonic() < deadline:
        frame, geometry = _grab_client(hwnd)
        try:
            decoded = decode_barcode(frame)
        except ValueError:
            decoded = None
        if decoded and decoded["index"] == expected:
            stable = _next_marker_stability(stable, last, decoded["index"], expected)
            if stable >= stable_polls:
                return {"frame": frame, "decoded": decoded, "geometry": geometry, "stable_polls": stable}
        elif decoded and 0 <= decoded["index"] < EXPECTED_TOTAL and decoded["index"] > expected:
            raise RuntimeError(f"showcase advanced past expected marker {expected} to {decoded['index']}")
        else:
            stable = _next_marker_stability(stable, last, decoded["index"] if decoded else None, expected)
        last = decoded["index"] if decoded else None
        time.sleep(0.01)
    raise TimeoutError(f"timed out waiting for stable showcase marker {expected}")


def _wait_for_native_png(directory: Path, previous: set[Path], timeout: float) -> Path:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        created = sorted((path for path in directory.glob("*.png") if path not in previous), key=lambda path: path.stat().st_mtime_ns)
        if created:
            target = created[-1]
            size = target.stat().st_size
            time.sleep(0.03)
            if target.stat().st_size == size and size > 0:
                return target
        time.sleep(0.01)
    raise TimeoutError("native F12 screenshot was not written")


def _capture_native(hwnd: int, screenshots: Path, expected_index: int, timeout: float) -> tuple[Path, dict]:
    previous = set(screenshots.glob("*.png"))
    _press_f12(hwnd)
    path = _wait_for_native_png(screenshots, previous, timeout)
    with Image.open(path) as source:
        if source.size != EXPECTED_SIZE:
            raise ValueError(f"native F12 screenshot must be {EXPECTED_SIZE}, got {source.size}")
        image = source.convert("RGB")
    decoded = decode_barcode(image)
    if decoded["index"] != expected_index:
        raise RuntimeError(f"native screenshot marker {decoded['index']} != expected {expected_index}")
    return path, decoded


def _try_capture_native(hwnd: int, screenshots: Path, expected_index: int, timeout: float) -> tuple[Path | None, dict | None, str]:
    try:
        path, decoded = _capture_native(hwnd, screenshots, expected_index, timeout)
        return path, decoded, "valid_native_f12_png"
    except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def _save_client_fallback(observation: dict, target: Path, expected_index: int) -> tuple[dict, dict]:
    geometry = observation["geometry"]
    observed = geometry.get("observed_client_size")
    normalization = geometry.get("normalization")
    if observed not in (list(EXPECTED_SIZE), list(OBSERVED_CLIENT_SIZE)):
        raise ValueError(
            f"client fallback requires observed {EXPECTED_SIZE} or {OBSERVED_CLIENT_SIZE}, got {observed}"
        )
    if observed == list(EXPECTED_SIZE) and normalization != NORMALIZATION_NONE:
        raise ValueError("exact client fallback must not normalize")
    if observed == list(OBSERVED_CLIENT_SIZE) and normalization != NORMALIZATION_NEAREST:
        raise ValueError("scaled client fallback must use nearest-neighbor normalization")
    frame = observation["frame"]
    decoded = decode_barcode(frame)
    if decoded["index"] != expected_index:
        raise RuntimeError(f"stable client marker {decoded['index']} != expected {expected_index}")
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.save(target, format="PNG", optimize=False, compress_level=1)
    return decoded, geometry


def _package_facts(package_dir: Path, manifest_path: Path) -> dict:
    manifest = load_json(manifest_path)
    if manifest.get("engine_build") != 7949 or manifest.get("schema_version") != 2:
        raise ValueError("package manifest is not the pinned Build 7949 schema")
    exe = package_dir / "OpenBOR.exe"
    paks = list((package_dir / "Paks").glob("*.pak"))
    if not exe.is_file() or len(paks) != 1:
        raise ValueError("clean package must contain OpenBOR.exe and exactly one sibling Paks/*.pak")
    if (package_dir / "data").exists():
        raise ValueError("clean package must not contain a loose data tree")
    provenance = manifest.get("pose_showcase_provenance", {})
    if provenance.get("pose_count") != EXPECTED_TOTAL or provenance.get("baseline_index") != BASELINE_INDEX:
        raise ValueError("package manifest showcase provenance does not match the 460-pose capture contract")
    file_hashes = {item["path"]: item["sha256"] for item in manifest.get("files", [])}
    for key, local_value, package_value in (
        ("harness_sha256", "openbor/data/scripts/entity_tech_demo.c", "data/scripts/entity_tech_demo.c"),
        ("overlay_sha256", "openbor/data/scripts/entity_pose_overlay.c", "data/scripts/entity_pose_overlay.c"),
    ):
        local = ROOT / local_value
        expected = provenance.get(key)
        if not local.is_file() or sha256(local) != expected or file_hashes.get(package_value) != expected:
            raise ValueError(f"package manifest {key} is stale")
    pak = paks[0]
    expected_exe = manifest["runtime_executable"]
    if exe.stat().st_size != int(expected_exe["size"]) or sha256(exe) != expected_exe["sha256"]:
        raise ValueError("package OpenBOR.exe does not match package manifest")
    if pak.stat().st_size != int(manifest["size"]) or sha256(pak) != manifest["sha256"]:
        raise ValueError("runtime PAK does not match package manifest")
    return {
        "package_manifest_path": repo_path(manifest_path),
        "package_manifest_sha256": sha256(manifest_path),
        "pak_path": repo_path(pak),
        "pak_sha256": sha256(pak),
        "pak_size": pak.stat().st_size,
        "pak_file_count": int(manifest["file_count"]),
        "exe_path": repo_path(exe),
        "exe_sha256": sha256(exe),
        "exe_size": exe.stat().st_size,
        "engine_build": 7949,
        "engine_reported_commit": manifest.get("engine_reported_commit"),
    }


def _record_payload(
    run_id: str,
    template: PoseTemplate,
    screenshot: Path,
    decoded: dict,
    analysis: dict,
    baseline: dict,
    package: dict,
    method: str,
    geometry: dict,
    stable_polls: int,
    captured_at_utc: str,
) -> dict:
    return {
        "schema_version": 2,
        "evidence_kind": "openbor_build7949_pose_capture",
        "run_id": run_id,
        "global_index": template.global_index,
        "entity": template.entity,
        "pose_id": template.pose_id,
        "group": template.group,
        "model_animation": template.model_animation,
        "animation_constant": template.animation_constant,
        "frame_index": template.frame_index,
        "hold_ticks": template.hold_ticks,
        "source": {
            "path": template.source_path,
            "generated_path": template.generated_path,
            "sha256": template.sprite_sha256,
            "palette_sha256": template.palette_sha256,
            "opaque_mask_sha256": template.opaque_mask_sha256,
            "opaque_pixels": template.opaque_pixels,
        },
        "package": package,
        "baseline": baseline,
        "capture": {
            "path": repo_path(screenshot),
            "sha256": sha256(screenshot),
            "width": EXPECTED_SIZE[0],
            "height": EXPECTED_SIZE[1],
            "method": method,
            "source_size": geometry["source_size"],
            "observed_client_size": geometry["observed_client_size"] if method != METHOD_NATIVE_F12 else None,
            "normalization": geometry["normalization"],
            "stable_marker_polls": stable_polls,
            "marker_source": "level updatedscript after entity queue at hud_z+100",
            "decoded_index": decoded["index"],
            "barcode_bits": decoded["bits"],
            "barcode_parity": decoded["parity"],
            "screen_root": list(SCREEN_ROOT),
            "model_root": list(MODEL_ROOT),
            "direction": DIRECTION,
            "roi": list(ROI),
            **analysis,
        },
        "captured_at_utc": captured_at_utc,
        "status": analysis["status"],
    }


def build_contact_sheet(records: list[dict], output: Path) -> None:
    columns = 20
    tile_width, image_height, label_height = 96, 80, 12
    rows = math.ceil(len(records) / columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * (image_height + label_height)), (18, 18, 22))
    draw = ImageDraw.Draw(sheet)
    left, top, width, height = ROI
    for slot, record in enumerate(records):
        with Image.open(resolve_repo_path(record["capture"]["path"])) as source:
            screenshot = source.convert("RGB")
        crop = screenshot.crop((left, top, left + width, top + height)).resize((tile_width, image_height), Image.Resampling.NEAREST)
        x = (slot % columns) * tile_width
        y = (slot // columns) * (image_height + label_height)
        sheet.paste(crop, (x, y))
        draw.text((x + 1, y + image_height + 1), f"{record['global_index']:03d} {record['pose_id'][:11]}", fill=(240, 240, 240))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, optimize=False)


def run_capture(args: argparse.Namespace) -> dict:
    if args.stable_polls < 2:
        raise ValueError("stable marker capture requires at least two consecutive decoded polls")
    package_dir = args.package_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f"evidence output must be empty for a new run: {output}")
    screenshots_output = output / "screenshots"
    records_output = output / "records"
    templates = build_schedule()
    package = _package_facts(package_dir, args.package_manifest.resolve())
    screenshots_output.mkdir(exist_ok=True)
    records_output.mkdir(exist_ok=True)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}"
    _configure_dpi_awareness()
    process = subprocess.Popen([str(package_dir / "OpenBOR.exe")], cwd=package_dir)
    captured_poses: list[CapturedPose] = []
    records: list[dict] = []
    try:
        try:
            hwnd = _find_window(process.pid, args.launch_timeout)
            _position_capture_window(hwnd)
            screenshots = package_dir / "ScreenShots"
            screenshots.mkdir(exist_ok=True)
            baseline_observation = _wait_for_marker(hwnd, BASELINE_INDEX, args.pose_timeout, args.stable_polls)
            native_baseline, native_decoded, native_probe = _try_capture_native(
                hwnd, screenshots, BASELINE_INDEX, args.screenshot_timeout
            )
            baseline_path = screenshots_output / "baseline.png"
            if native_baseline is not None:
                method = METHOD_NATIVE_F12
                baseline_decoded = native_decoded
                baseline_geometry = {
                    "source_size": list(EXPECTED_SIZE),
                    "observed_client_size": None,
                    "normalization": NORMALIZATION_NONE,
                }
                shutil.copy2(native_baseline, baseline_path)
            else:
                observed = baseline_observation["geometry"]["observed_client_size"]
                method = METHOD_CLIENT_EXACT if observed == list(EXPECTED_SIZE) else METHOD_CLIENT_NORMALIZED
                baseline_decoded, baseline_geometry = _save_client_fallback(
                    baseline_observation, baseline_path, BASELINE_INDEX
                )
            baseline_captured_at = datetime.now(timezone.utc).isoformat()

            # Live phase: decode and persist each stable frame only.  Source
            # matching, hashes, record JSON, and contact sheets are deliberately
            # deferred until the complete sequence is captured and OpenBOR exits.
            for template in templates:
                observation = _wait_for_marker(hwnd, template.global_index, args.pose_timeout, args.stable_polls)
                evidence_png = screenshots_output / f"{template.global_index:03d}_{template.pose_id}.png"
                if method == METHOD_NATIVE_F12:
                    native, decoded = _capture_native(hwnd, screenshots, template.global_index, args.screenshot_timeout)
                    shutil.copy2(native, evidence_png)
                    geometry = {
                        "source_size": list(EXPECTED_SIZE),
                        "observed_client_size": None,
                        "normalization": NORMALIZATION_NONE,
                    }
                else:
                    decoded, geometry = _save_client_fallback(observation, evidence_png, template.global_index)
                captured_poses.append(
                    CapturedPose(
                        template=template,
                        screenshot_path=evidence_png,
                        decoded=decoded,
                        geometry=geometry,
                        stable_polls=observation["stable_polls"],
                        captured_at_utc=datetime.now(timezone.utc).isoformat(),
                    )
                )
            capture_completed_at = datetime.now(timezone.utc).isoformat()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        if len(captured_poses) != EXPECTED_TOTAL:
            raise ValueError(f"capture phase produced {len(captured_poses)} of {EXPECTED_TOTAL} required pose frames")
        if [item.template.global_index for item in captured_poses] != list(range(EXPECTED_TOTAL)):
            raise ValueError("capture phase pose order is incomplete or non-deterministic")

        # Offline phase: all expensive work starts only after the runtime is
        # terminated, so analysis cannot cause the showcase to skip short holds.
        with Image.open(baseline_path) as source:
            baseline_image = source.convert("RGB")
        if baseline_image.size != EXPECTED_SIZE:
            raise ValueError(f"evidence baseline must be {EXPECTED_SIZE}, got {baseline_image.size}")
        baseline = {
            "path": repo_path(baseline_path),
            "sha256": sha256(baseline_path),
            "method": method,
            "source_size": baseline_geometry["source_size"],
            "observed_client_size": baseline_geometry["observed_client_size"],
            "normalization": baseline_geometry["normalization"],
            "stable_marker_polls": baseline_observation["stable_polls"],
            "decoded_index": baseline_decoded["index"],
            "barcode_bits": baseline_decoded["bits"],
            "width": EXPECTED_SIZE[0],
            "height": EXPECTED_SIZE[1],
            "captured_at_utc": baseline_captured_at,
        }
        for captured in captured_poses:
            with Image.open(captured.screenshot_path) as source:
                capture = source.convert("RGB")
            analysis = analyze_capture(capture, baseline_image, captured.template, templates)
            if analysis["status"] != "pass":
                raise ValueError(f"{captured.template.pose_id}: visual verification failed: {analysis['failures']}")
            record = _record_payload(
                run_id, captured.template, captured.screenshot_path, captured.decoded, analysis, baseline, package,
                method, captured.geometry, captured.stable_polls, captured.captured_at_utc
            )
            record_path = records_output / f"{captured.template.global_index:03d}_{captured.template.pose_id}.json"
            write_json(record_path, record)
            records.append(record)
        sheet = output / "contact_sheet.png"
        build_contact_sheet(records, sheet)
        record_entries = []
        for record in records:
            path = records_output / f"{record['global_index']:03d}_{record['pose_id']}.json"
            record_entries.append({"global_index": record["global_index"], "pose_id": record["pose_id"], "path": repo_path(path), "sha256": sha256(path)})
        digest = sha256_bytes("".join(f"{item['global_index']}:{item['pose_id']}:{item['sha256']}\n" for item in record_entries).encode("ascii"))
        summary = {
            "schema_version": 2,
            "evidence_kind": "openbor_build7949_all_pose_capture_run",
            "status": "pass",
            "run_id": run_id,
            "capture_method": method,
            "method_selection": {
                "preferred": METHOD_NATIVE_F12,
                "selected": method,
                "native_f12_probe": native_probe,
            },
            "capture_contract": capture_contract(),
            "package": package,
            "baseline": baseline,
            "pose_count": len(records),
            "entity_counts": dict(ENTITY_COUNTS),
            "records": record_entries,
            "records_digest_sha256": digest,
            "contact_sheet": {"path": repo_path(sheet), "sha256": sha256(sheet)},
            "capture_completed_at_utc": capture_completed_at,
            "analysis_completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        write_json(output / "summary.json", summary)
        return summary
    except Exception as exc:
        failure = {
            "schema_version": 2,
            "status": "fail",
            "run_id": run_id,
            "error": str(exc),
            "captured_frames": len(captured_poses),
            "validated_records": len(records),
        }
        write_json(output / "failure.json", failure)
        raise


def capture_contract() -> dict:
    return {
        "resolution": list(EXPECTED_SIZE),
        "marker_source": "level updatedscript after entity queue",
        "barcode": {
            "strip": list(BARCODE_STRIP),
            "start": [BARCODE_START_X, BARCODE_Y],
            "payload_origin": [BARCODE_PAYLOAD_X, BARCODE_Y],
            "parity": [BARCODE_PARITY_X, BARCODE_Y],
            "end": [BARCODE_END_X, BARCODE_Y],
            "cell": list(BARCODE_CELL),
            "pitch": BARCODE_PITCH,
            "payload_bits": BARCODE_PAYLOAD_BITS,
            "total_cells": BARCODE_TOTAL_CELLS,
            "layout": "sentinel_1,twelve_bit_lsb_first_index,even_parity,sentinel_1",
            "z": f"openborvariant(hud_z)+{BARCODE_Z_OFFSET}",
            "baseline_index": BASELINE_INDEX,
            "pose_indexes": [0, EXPECTED_TOTAL - 1],
        },
        "pose_text_origin": [8, 8],
        "screen_root": list(SCREEN_ROOT),
        "model_root": list(MODEL_ROOT),
        "direction": DIRECTION,
        "roi": list(ROI),
        "hold_ticks": {"black_dave": DAVE_HOLD_TICKS, "homeless_man": ENEMY_HOLD_TICKS, "police_officer": ENEMY_HOLD_TICKS},
        "alignment_radius": ALIGN_RADIUS,
        "minimum_stable_marker_polls": 2,
        "candidate_scope": "same_entity_and_pose_group",
        "thresholds": {
            "rgb_exact_min": RGB_EXACT_MIN,
            "silhouette_iou_min": SILHOUETTE_IOU_MIN,
            "best_margin_min": BEST_MARGIN_MIN,
        },
        "capture_methods": {
            "preferred": METHOD_NATIVE_F12,
            "fallback_exact": METHOD_CLIENT_EXACT,
            "fallback_normalized": METHOD_CLIENT_NORMALIZED,
            "fallback_exact_client_size": list(EXPECTED_SIZE),
            "fallback_observed_client_size": list(OBSERVED_CLIENT_SIZE),
            "normalized_size": list(EXPECTED_SIZE),
            "fallback_resampling": NORMALIZATION_NEAREST,
            "selection": "probe_native_f12_at_baseline_then_use_one_method_for_entire_run",
        },
    }


def run_self_test() -> dict:
    # Barcode round trip, including all production indexes.
    for index in [*range(EXPECTED_TOTAL), BASELINE_INDEX]:
        image = Image.new("RGB", EXPECTED_SIZE, (23, 31, 47))
        draw_synthetic_barcode(image, index)
        if decode_barcode(image)["index"] != index:
            raise AssertionError(f"barcode round trip failed for {index}")
    tampered = Image.new("RGB", EXPECTED_SIZE, (0, 0, 0))
    draw_synthetic_barcode(tampered, 17)
    ImageDraw.Draw(tampered).rectangle(
        (BARCODE_PARITY_X, BARCODE_Y, BARCODE_PARITY_X + BARCODE_CELL[0] - 1, BARCODE_Y + BARCODE_CELL[1] - 1),
        fill=(255, 255, 255),
    )
    try:
        decode_barcode(tampered)
    except ValueError:
        parity_rejected = True
    else:
        parity_rejected = False
    if not parity_rejected:
        raise AssertionError("tampered barcode parity was accepted")

    stable = 0
    last = None
    for decoded_index in (17, None, 17, 18, 17):
        stable = _next_marker_stability(stable, last, decoded_index, 17)
        last = decoded_index
    if stable != 1:
        raise AssertionError("unstable marker sequence was accepted as stable")
    stable = _next_marker_stability(stable, last, 17, 17)
    if stable != 2:
        raise AssertionError("two consecutive expected markers did not satisfy stability")

    native_pattern = Image.new("RGB", EXPECTED_SIZE, (23, 31, 47))
    draw_synthetic_barcode(native_pattern, 219)
    scaled_client = native_pattern.resize(OBSERVED_CLIENT_SIZE, Image.Resampling.NEAREST)
    normalized, geometry = normalize_client_capture(scaled_client)
    if normalized.tobytes() != native_pattern.tobytes() or decode_barcode(normalized)["index"] != 219:
        raise AssertionError("960x540 nearest-neighbor client normalization changed source pixels")
    if geometry != {
        "source_size": list(OBSERVED_CLIENT_SIZE),
        "observed_client_size": list(OBSERVED_CLIENT_SIZE),
        "normalization": NORMALIZATION_NEAREST,
    }:
        raise AssertionError(f"unexpected normalized client geometry: {geometry}")
    exact, exact_geometry = normalize_client_capture(native_pattern)
    if exact.tobytes() != native_pattern.tobytes() or decode_barcode(exact)["index"] != 219:
        raise AssertionError("640x360 exact client capture changed source pixels")
    if exact_geometry != {
        "source_size": list(EXPECTED_SIZE),
        "observed_client_size": list(EXPECTED_SIZE),
        "normalization": NORMALIZATION_NONE,
    }:
        raise AssertionError(f"unexpected exact client geometry: {exact_geometry}")
    try:
        normalize_client_capture(Image.new("RGB", (800, 450)))
    except ValueError:
        unsupported_geometry_rejected = True
    else:
        unsupported_geometry_rejected = False
    if not unsupported_geometry_rejected:
        raise AssertionError("unsupported client geometry was accepted")

    run_source = inspect.getsource(run_capture)
    offline_marker = run_source.index("# Offline phase")
    if "analyze_capture(" in run_source[:offline_marker]:
        raise AssertionError("pixel analysis regressed into the live capture phase")
    if run_source.find("process.wait", 0, offline_marker) < 0:
        raise AssertionError("offline analysis begins before runtime termination")

    # Pixel matcher positive and negative cases use a real approved source so
    # palette/transparency semantics match production without writing artifacts.
    templates = build_schedule()
    template = templates[0]
    baseline = Image.new("RGB", EXPECTED_SIZE, (37, 43, 53))
    draw_synthetic_barcode(baseline, BASELINE_INDEX)
    capture = baseline.copy()
    source = template.source_image().convert("RGBA")
    left, top, _, _ = ROI
    capture.paste(source.convert("RGB"), (left, top), source.getchannel("A"))
    draw_synthetic_barcode(capture, template.global_index)
    positive = analyze_capture(capture, baseline, template, templates[:2])
    if positive["status"] != "pass":
        raise AssertionError(f"synthetic positive failed: {positive}")
    negative = capture.copy()
    negative.putpixel((left + MODEL_ROOT[0], top + MODEL_ROOT[1] - 20), (255, 0, 255))
    # Broad tamper guarantees the cryptographic pixel gate trips.
    ImageDraw.Draw(negative).rectangle((left + 20, top + 20, left + 150, top + 120), fill=(255, 0, 255))
    rejected = analyze_capture(negative, baseline, template, templates[:2])["status"] == "fail"
    if not rejected:
        raise AssertionError("synthetic pixel tamper was accepted")
    return {
        "status": "pass",
        "barcode_round_trips": EXPECTED_TOTAL + 1,
        "parity_tamper_rejected": True,
        "unstable_marker_rejected": True,
        "normalized_960x540_pixel_exact": True,
        "unsupported_geometry_rejected": True,
        "analysis_deferred_until_after_capture": True,
        "pixel_tamper_rejected": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, default=Path("build/entity_tech_demo/runtime"))
    parser.add_argument("--package-manifest", type=Path, default=Path("openbor/releases/entity_tech_demo/package_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("build/entity_pose_evidence"))
    parser.add_argument("--launch-timeout", type=float, default=45.0)
    parser.add_argument("--pose-timeout", type=float, default=15.0)
    parser.add_argument("--screenshot-timeout", type=float, default=1.0)
    parser.add_argument("--stable-polls", type=int, default=2)
    parser.add_argument("--print-contract", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.print_contract:
        print(json.dumps(capture_contract(), indent=2))
        return 0
    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return 0
    summary = run_capture(args)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
