"""Build the complete runtime animation library from the detailed source art.

The source atlases already contain the character designs and key poses.  This
builder maps those authored anticipation, contact, recoil, recovery, gait and
personality drawings into rooted runtime strips.  It preserves the intended
silhouettes and source-root registration; no strip is padded with duplicate,
synthetic-deformation, or translated-only cells.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


DIRECT_REFERENCE_SPECS: dict[tuple[str, str], tuple[str, int, int]] = {
    ("chief", "move"): ("chief_run_reference_v1.png", 4, 3),
    ("chief", "sit"): ("chief_sit_reference_v1.png", 4, 4),
    ("stick", "walk"): ("enemy_stick_walk_reference_v1.png", 4, 3),
    ("cart", "walk"): ("enemy_cart_walk_reference_v1.png", 4, 3),
    ("whip", "walk"): ("enemy_whip_walk_reference_v1.png", 4, 3),
    ("pipe", "walk"): ("enemy_pipe_walk_reference_v1.png", 4, 3),
    ("couch", "walk"): ("couch_waddle_reference_v1.png", 4, 4),
    ("chief", "maul"): ("chief_maul_reference_v1.png", 4, 2),
}
DIRECT_RENDER_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("stick", "walk"): (158, 116),
    ("cart", "walk"): (158, 118),
    ("whip", "walk"): (158, 112),
    ("pipe", "walk"): (158, 116),
    ("couch", "walk"): (112, 98),
    ("chief", "maul"): (252, 124),
}

from src.animation_manifest import (  # noqa: E402
    ANIMATION_CLIPS,
    BASE_POSES_PER_CLIP,
    CHIEF_STATES,
    COUCH_STATES,
    ENEMY_KINDS,
    ENEMY_STATES,
    JERRY_STATES,
    PLAYER_STATES,
    total_authored_poses,
)


@dataclass(frozen=True, slots=True)
class PoseTransform:
    angle: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    offset_x: int = 0
    offset_y: int = 0


PROFILES: dict[str, tuple[PoseTransform, ...]] = {
    "idle": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-0.8, 1.01, 0.99, -1),
        PoseTransform(-1.2, 1.00, 1.02, -1, -1), PoseTransform(-0.4, 0.99, 1.03, 0, -2),
        PoseTransform(0.8, 1.01, 1.01, 1, -1), PoseTransform(1.2, 1.02, 0.99, 1),
        PoseTransform(0.4, 1.00, 1.01), PoseTransform(0, 1.00, 1.00),
    ),
    "chief_idle_extended": (
        PoseTransform(0.0, 1.000, 1.000), PoseTransform(-0.7, 1.006, 0.997),
        PoseTransform(-1.1, 1.010, 0.994), PoseTransform(-0.5, 1.014, 0.991),
        PoseTransform(0.3, 1.016, 0.990), PoseTransform(0.9, 1.012, 0.993),
        PoseTransform(1.2, 1.008, 0.996), PoseTransform(0.6, 1.003, 1.001),
        PoseTransform(-2.2, 1.010, 0.990), PoseTransform(-0.8, 0.996, 1.006),
        PoseTransform(-0.4, 1.002, 1.002), PoseTransform(0.5, 1.007, 0.997),
    ),
    "enemy_idle_extended": (
        PoseTransform(0.0, 1.000, 1.000), PoseTransform(-0.8, 1.007, 0.996),
        PoseTransform(-1.3, 1.011, 0.992), PoseTransform(-0.6, 1.015, 0.989),
        PoseTransform(0.2, 1.018, 0.987), PoseTransform(0.9, 1.013, 0.991),
        PoseTransform(1.4, 1.008, 0.995), PoseTransform(0.7, 1.002, 1.001),
        PoseTransform(2.2, 1.012, 0.989), PoseTransform(-1.0, 0.995, 1.008),
        PoseTransform(-2.2, 1.014, 0.987), PoseTransform(0.6, 1.009, 0.995),
    ),
    "couch_idle_extended": (
        PoseTransform(0.0, 1.000, 1.000), PoseTransform(-0.6, 1.008, 0.996),
        PoseTransform(-1.0, 1.014, 0.991), PoseTransform(-0.4, 1.019, 0.987),
        PoseTransform(0.4, 1.022, 0.985), PoseTransform(1.0, 1.016, 0.990),
        PoseTransform(1.3, 1.009, 0.995), PoseTransform(0.7, 1.002, 1.001),
        PoseTransform(-0.2, 0.996, 1.006), PoseTransform(-0.9, 0.994, 1.009),
        PoseTransform(-0.3, 1.004, 1.001), PoseTransform(0.6, 1.011, 0.994),
    ),
    "jerry_extended": (
        PoseTransform(0.0, 1.000, 1.000), PoseTransform(-0.5, 1.006, 0.997),
        PoseTransform(-1.0, 1.011, 0.993), PoseTransform(-0.4, 1.016, 0.990),
        PoseTransform(0.4, 1.019, 0.988), PoseTransform(1.0, 1.014, 0.992),
        PoseTransform(1.3, 1.008, 0.996), PoseTransform(0.7, 1.002, 1.001),
        PoseTransform(-0.2, 0.998, 1.004), PoseTransform(-0.8, 0.996, 1.006),
        PoseTransform(-0.3, 1.003, 1.002), PoseTransform(0.6, 1.009, 0.995),
    ),
    "chief_sit_extended": (
        PoseTransform(0.0, 1.000, 1.000), PoseTransform(-0.8, 1.018, 0.955, 0, 3),
        PoseTransform(-1.5, 1.028, 0.920, 0, 6), PoseTransform(-2.0, 1.035, 0.895, 0, 8),
        PoseTransform(-1.2, 1.040, 0.880, 0, 10), PoseTransform(-0.5, 1.044, 0.872, 0, 11),
        PoseTransform(0.3, 1.046, 0.868, 0, 11), PoseTransform(1.0, 1.043, 0.874, 0, 10),
        PoseTransform(1.6, 1.038, 0.882, 0, 10), PoseTransform(1.1, 1.034, 0.890, 0, 9),
        PoseTransform(0.4, 1.037, 0.884, 0, 10), PoseTransform(-0.4, 1.041, 0.878, 0, 11),
        PoseTransform(-1.1, 1.045, 0.870, 0, 11), PoseTransform(-0.6, 1.042, 0.876, 0, 10),
        PoseTransform(0.2, 1.038, 0.884, 0, 10), PoseTransform(0.8, 1.034, 0.892, 0, 9),
    ),
    "move_extended": (
        PoseTransform(-2.0, 1.018, 0.982, -2), PoseTransform(-1.2, 1.010, 1.000, -1, -1),
        PoseTransform(-0.4, 0.995, 1.018, 0, -2), PoseTransform(0.7, 1.006, 1.006, 1, -1),
        PoseTransform(1.7, 1.022, 0.980, 2), PoseTransform(2.3, 1.028, 0.974, 2, 1),
        PoseTransform(1.8, 1.018, 0.984, 1), PoseTransform(1.0, 1.008, 1.002, 1, -1),
        PoseTransform(0.2, 0.994, 1.020, 0, -2), PoseTransform(-0.9, 1.007, 1.005, -1, -1),
        PoseTransform(-1.8, 1.021, 0.979, -2), PoseTransform(-2.4, 1.027, 0.973, -2, 1),
    ),
    "move": (
        PoseTransform(-2.5, 1.02, 0.98, -2), PoseTransform(-1.5, 1.00, 1.03, -1, -2),
        PoseTransform(-0.5, 0.98, 1.01, 0, -1), PoseTransform(1.5, 1.02, 0.97, 2),
        PoseTransform(2.5, 1.03, 0.98, 2), PoseTransform(1.2, 1.00, 1.03, 1, -2),
        PoseTransform(1.8, 0.99, 1.02, 1, -1), PoseTransform(-1.7, 1.02, 0.98, -1),
    ),
    "attack": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-2.0, 0.98, 1.03, -2, -1),
        PoseTransform(-4.0, 1.01, 0.99, -3), PoseTransform(-2.0, 1.05, 0.97, 1),
        PoseTransform(1.0, 1.08, 0.96, 4), PoseTransform(3.0, 1.05, 0.98, 3),
        PoseTransform(1.5, 1.02, 1.00, 1), PoseTransform(0, 1.00, 1.00),
    ),
    "ranged": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-1.5, 0.99, 1.02, -1),
        PoseTransform(-0.5, 1.02, 1.00, 1), PoseTransform(0.5, 1.05, 0.98, 3),
        PoseTransform(2.5, 1.03, 0.97, 2), PoseTransform(1.0, 1.01, 1.00, 1),
        PoseTransform(-0.5, 0.99, 1.01), PoseTransform(0, 1.00, 1.00),
    ),
    "dodge": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-2.5, 1.04, 0.91, -2, 4),
        PoseTransform(-4.5, 1.08, 0.84, -4, 8), PoseTransform(-5.5, 1.11, 0.78, -5, 12),
        PoseTransform(-3.5, 1.10, 0.80, -2, 11), PoseTransform(-1.5, 1.06, 0.88, 0, 7),
        PoseTransform(-0.5, 1.02, 0.96, 0, 2), PoseTransform(0, 1.00, 1.00),
    ),
    "hurt": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(3, 1.03, 0.98, 2),
        PoseTransform(7, 1.05, 0.96, 4, 1), PoseTransform(11, 1.07, 0.93, 6, 4),
        PoseTransform(8, 1.08, 0.91, 5, 6), PoseTransform(5, 1.05, 0.95, 3, 4),
        PoseTransform(2, 1.02, 0.98, 1, 2), PoseTransform(0, 1.00, 1.00),
    ),
    "down": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(8, 1.02, 0.98, 1, 2),
        PoseTransform(20, 1.01, 1.01, 3, 5), PoseTransform(38, 0.96, 1.05, 5, 9),
        PoseTransform(58, 0.88, 1.09, 7, 14), PoseTransform(75, 0.79, 1.13, 8, 18),
        PoseTransform(88, 0.70, 1.17, 8, 21), PoseTransform(90, 0.66, 1.20, 8, 23),
    ),
    "spawn": (
        PoseTransform(90, 0.66, 1.20, -6, 23), PoseTransform(76, 0.79, 1.13, -5, 18),
        PoseTransform(55, 0.88, 1.09, -4, 14), PoseTransform(36, 0.96, 1.05, -3, 9),
        PoseTransform(18, 1.05, 0.93, -2, 5), PoseTransform(7, 1.03, 0.97, -1, 2),
        PoseTransform(2, 1.01, 0.99), PoseTransform(0, 1.00, 1.00),
    ),
    "power": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-2, 0.98, 1.03, -1, -1),
        PoseTransform(-4, 1.00, 1.05, -2, -3), PoseTransform(-2, 1.04, 1.03, 0, -4),
        PoseTransform(1, 1.10, 0.98, 4, -3), PoseTransform(4, 1.13, 0.96, 6, -2),
        PoseTransform(2, 1.06, 0.99, 3, -1), PoseTransform(0, 1.00, 1.00),
    ),
    "air": (
        PoseTransform(0, 1.04, 0.91, 0, 5), PoseTransform(-4, 1.01, 0.98, -2, -5),
        PoseTransform(-7, 0.98, 1.03, -2, -12), PoseTransform(-3, 1.02, 1.01, 0, -17),
        PoseTransform(4, 1.12, 0.91, 5, -16), PoseTransform(7, 1.07, 0.95, 4, -10),
        PoseTransform(2, 1.04, 0.90, 1, 2), PoseTransform(0, 1.00, 1.00),
    ),
    "jump": (
        PoseTransform(0, 1.05, 0.88, 0, 7), PoseTransform(-3, 1.01, 0.97, -1, -4),
        PoseTransform(-5, 0.98, 1.04, -1, -12), PoseTransform(-1, 1.00, 1.05, 0, -18),
        PoseTransform(3, 1.02, 1.01, 1, -14), PoseTransform(5, 1.05, 0.96, 2, -6),
        PoseTransform(2, 1.07, 0.87, 1, 5), PoseTransform(0, 1.00, 1.00),
    ),
    "pet": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-2, 1.01, 0.97, -1, 2),
        PoseTransform(-4, 1.04, 0.91, -2, 6), PoseTransform(-6, 1.06, 0.86, -3, 9),
        PoseTransform(-5, 1.07, 0.84, -2, 10), PoseTransform(-3, 1.05, 0.89, -1, 7),
        PoseTransform(-1, 1.02, 0.96, 0, 3), PoseTransform(0, 1.00, 1.00),
    ),
    "refill": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-1, 1.01, 1.00, -1),
        PoseTransform(-2, 1.02, 0.99, -1, 1), PoseTransform(-3, 1.03, 0.98, -1, 2),
        PoseTransform(-2, 1.04, 0.97, 0, 2), PoseTransform(-1, 1.02, 0.99, 0, 1),
        PoseTransform(1, 1.01, 1.00, 1), PoseTransform(0, 1.00, 1.00),
    ),
    "pants": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(1, 1.01, 0.99, 1, 1),
        PoseTransform(2, 1.02, 0.96, 2, 3), PoseTransform(3, 1.03, 0.94, 2, 5),
        PoseTransform(2, 1.04, 0.92, 1, 6), PoseTransform(1, 1.03, 0.95, 1, 4),
        PoseTransform(0, 1.01, 0.98, 0, 2), PoseTransform(0, 1.00, 1.00),
    ),
    "refill_extended": (
        PoseTransform(0.0, 1.000, 1.000), PoseTransform(-0.8, 1.006, 0.996, -1),
        PoseTransform(-1.5, 1.012, 0.992, -1), PoseTransform(-1.1, 1.010, 0.994, -1),
        PoseTransform(-0.8, 1.008, 0.996, -1), PoseTransform(-1.1, 1.012, 0.992, -1, 1),
        PoseTransform(-1.3, 1.016, 0.988, 0, 1), PoseTransform(-1.2, 1.018, 0.987, 0, 2),
        PoseTransform(-1.0, 1.020, 0.986, 0, 2), PoseTransform(-0.6, 1.018, 0.988, 1, 2),
        PoseTransform(-0.2, 1.014, 0.992, 1, 1), PoseTransform(0.3, 1.010, 0.996, 1, 1),
        PoseTransform(0.7, 1.008, 0.998, 1), PoseTransform(0.4, 1.004, 1.000),
        PoseTransform(0.9, 1.006, 0.998, 1), PoseTransform(1.4, 1.008, 0.996, 1),
    ),
    "pants_extended": (
        PoseTransform(0.0, 1.000, 1.000), PoseTransform(0.6, 1.006, 0.996, 1),
        PoseTransform(1.1, 1.012, 0.992, 1, 1), PoseTransform(0.8, 1.008, 0.994, 1, 2),
        PoseTransform(1.2, 1.012, 0.988, 1, 3), PoseTransform(1.4, 1.014, 0.985, 2, 3),
        PoseTransform(1.5, 1.016, 0.982, 2, 4), PoseTransform(1.9, 1.026, 0.972, 2, 6),
        PoseTransform(1.2, 1.020, 0.978, 2, 5), PoseTransform(0.8, 1.022, 0.976, 1, 6),
        PoseTransform(0.3, 1.018, 0.980, 1, 5), PoseTransform(-0.5, 1.012, 0.987, 0, 4),
        PoseTransform(-1.4, 1.008, 0.995, -1, 3), PoseTransform(-0.9, 1.008, 0.994, -1, 3),
        PoseTransform(-0.6, 1.010, 0.992, 0, 3), PoseTransform(-0.3, 1.006, 0.996, 0, 1),
    ),
    "sit": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(0, 1.03, 0.91, 0, 5),
        PoseTransform(0, 1.06, 0.82, 0, 10), PoseTransform(-1, 1.08, 0.75, -1, 14),
        PoseTransform(-2, 1.07, 0.76, -2, 14), PoseTransform(2, 1.07, 0.76, 2, 14),
        PoseTransform(1, 1.08, 0.75, 1, 14), PoseTransform(0, 1.07, 0.76, 0, 14),
    ),
    "command": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-2, 1.02, 0.97, -1, 2),
        PoseTransform(-4, 1.06, 0.89, -3, 6), PoseTransform(-5, 1.12, 0.82, -5, 10),
        PoseTransform(-2, 1.10, 0.88, 0, 5), PoseTransform(2, 1.08, 0.92, 4, 2),
        PoseTransform(4, 1.04, 0.96, 3, 1), PoseTransform(0, 1.00, 1.00),
    ),
    "laugh": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-2, 0.99, 1.02, -1, -1),
        PoseTransform(-4, 1.03, 0.99, -2), PoseTransform(-6, 1.06, 0.96, -3, 2),
        PoseTransform(-4, 1.09, 0.94, -2, 4), PoseTransform(2, 1.07, 0.96, 2, 3),
        PoseTransform(3, 1.03, 0.99, 2, 1), PoseTransform(0, 1.00, 1.00),
    ),
    "victory": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-1, 1.01, 1.00, -1),
        PoseTransform(-2, 1.02, 1.01, -1, -1), PoseTransform(0, 1.03, 0.99, 0),
        PoseTransform(2, 1.04, 0.98, 1, -1), PoseTransform(3, 1.03, 0.99, 2),
        PoseTransform(1, 1.02, 1.01, 1, -1), PoseTransform(0, 1.00, 1.00),
    ),
    "support": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-0.7, 1.01, 1.00, -1),
        PoseTransform(-1.5, 1.02, 0.99, -1, 1), PoseTransform(-0.4, 1.01, 1.01, 0, -1),
        PoseTransform(1.0, 1.02, 0.99, 1), PoseTransform(1.7, 1.01, 1.00, 1, 1),
        PoseTransform(0.6, 1.00, 1.01, 0, -1), PoseTransform(-0.3, 1.01, 1.00),
    ),
    "talk": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-1.2, 1.01, 1.00, -1),
        PoseTransform(-2.0, 1.02, 0.99, -2, -1), PoseTransform(-0.8, 1.03, 0.98, -1),
        PoseTransform(1.0, 1.04, 0.98, 1, -1), PoseTransform(2.2, 1.03, 0.99, 2),
        PoseTransform(0.8, 1.01, 1.01, 1), PoseTransform(-0.4, 1.00, 1.01),
    ),
    "point": (
        PoseTransform(0, 1.00, 1.00), PoseTransform(-1.0, 1.01, 1.00, -1),
        PoseTransform(-2.5, 1.03, 0.98, -2, -1), PoseTransform(-3.5, 1.05, 0.97, -3, -1),
        PoseTransform(-1.5, 1.07, 0.97, 1, -1), PoseTransform(0.5, 1.05, 0.98, 2),
        PoseTransform(1.2, 1.02, 1.00, 1), PoseTransform(0.4, 1.01, 1.00),
    ),
    "ride": (
        PoseTransform(-0.6, 1.00, 1.00, -1), PoseTransform(-0.2, 1.01, 0.99, 0, -1),
        PoseTransform(0.5, 1.00, 1.01, 1), PoseTransform(0.9, 1.01, 0.99, 1, -1),
        PoseTransform(0.2, 1.00, 1.01), PoseTransform(-0.5, 1.01, 0.99, -1, -1),
        PoseTransform(-0.9, 1.00, 1.01, -1), PoseTransform(0.4, 1.01, 1.00, 1, -1),
    ),
}

# The original source art has strong attack silhouettes.  These profiles keep
# their perspective while preserving a single aspect ratio for every hero
# action phase—no rubber-band squash/stretch or mid-combo height collapse.
_HERO_STABLE_ACTIONS = frozenset(
    {
        "attack_1", "attack_2", "attack_3", "attack_4", "heavy",
        "ranged", "dodge", "hurt", "super", "air_attack", "jump", "pet",
    }
)
_HERO_ACTION_OFFSETS = ((0, 0), (-1, 0), (-2, -1), (0, -1), (2, -1), (2, 0), (1, 0), (0, 0))


def _uniform_action_profile(scales: tuple[float, ...]) -> tuple[PoseTransform, ...]:
    """Make authored action beats lively without deforming actor proportions."""

    return tuple(
        PoseTransform(0.0, scale, scale, offset_x, offset_y)
        for scale, (offset_x, offset_y) in zip(scales, _HERO_ACTION_OFFSETS, strict=True)
    )


PROFILES["hero_combat_stable"] = _uniform_action_profile(
    (1.03, 1.05, 1.08, 1.11, 1.13, 1.10, 1.07, 1.04)
)
PROFILES["dave_combat_stable"] = _uniform_action_profile(
    (1.14, 1.16, 1.18, 1.21, 1.23, 1.20, 1.17, 1.14)
)


HERO_SOURCES = {
    "idle": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    # Walk uses the dedicated twelve-drawing reference sheets below, not
    # transformed duplicates from the five-by-four combat source atlases.
    "walk": tuple(range(12)),
    "attack_1": (10, 10, 11, 12, 12, 11, 10, 0),
    "attack_2": (10, 11, 12, 13, 14, 13, 11, 10),
    "attack_3": (10, 13, 15, 16, 17, 16, 13, 10),
    "attack_4": (10, 11, 13, 14, 16, 14, 11, 10),
    "heavy": (10, 11, 15, 16, 17, 16, 13, 10),
    "ranged": (0, 3, 10, 15, 16, 15, 3, 0),
    "dodge": (0, 5, 6, 7, 8, 9, 6, 0),
    "hurt": (10, 13, 18, 18, 17, 13, 10, 0),
    "down": (10, 13, 18, 18, 18, 18, 18, 18),
    "super": (0, 3, 10, 15, 19, 19, 15, 0),
    "air_attack": (10, 15, 16, 17, 18, 17, 15, 10),
    "jump": (0, 5, 10, 15, 17, 15, 5, 0),
    "pet": (0, 1, 2, 3, 4, 3, 2, 0),
    "refill": (0, 1, 2, 3, 4, 3, 2, 0),
    "pants": (4, 3, 2, 1, 0, 1, 2, 4),
}

# Canonical ``(rear, lead)`` hand centres authored against the untrimmed source
# cells.  These are semantic landmarks, not palette samples: shoulders, faces,
# raised sneakers and impact flashes can share Dave's warm colors, so a color
# extreme can never reliably identify a fist.  The builder carries these exact
# points through the same crop/scale/rotation/root transform as each rendered
# cel and emits the resulting runtime metadata beside the atlas.
DAVE_COMBAT_FIST_LANDMARKS: dict[int, tuple[tuple[int, int], tuple[int, int]]] = {
    0: ((45, 42), (75, 43)),
    1: ((48, 54), (70, 44)),
    2: ((48, 50), (74, 44)),
    3: ((60, 69), (79, 29)),
    4: ((46, 42), (74, 44)),
    5: ((47, 69), (79, 61)),
    6: ((47, 70), (75, 63)),
    7: ((51, 70), (80, 64)),
    8: ((48, 70), (79, 64)),
    9: ((47, 69), (78, 63)),
    10: ((55, 52), (86, 58)),
    11: ((51, 49), (112, 50)),
    12: ((45, 58), (111, 51)),
    13: ((48, 53), (79, 29)),
    14: ((39, 55), (109, 49)),
    15: ((46, 32), (77, 63)),
    16: ((38, 62), (104, 53)),
    17: ((39, 66), (79, 43)),
    18: ((51, 64), (91, 57)),
    19: ((46, 46), (83, 41)),
}
DAVE_WALK_FIST_LANDMARKS: tuple[tuple[tuple[int, int], tuple[int, int]], ...] = (
    ((112, 252), (244, 248)),
    ((141, 270), (224, 269)),
    ((133, 253), (239, 248)),
    ((137, 252), (207, 252)),
    ((146, 269), (185, 253)),
    ((82, 276), (183, 253)),
    ((83, 193), (198, 180)),
    ((133, 225), (204, 202)),
    ((101, 205), (195, 181)),
    ((122, 221), (177, 190)),
    ((55, 178), (153, 184)),
    ((80, 206), (161, 192)),
)
# The two generated walk sheets render a character progressing horizontally
# through the source cells.  That is useful as a concept strip, but applying
# that built-in translation again to an actor already travelling in world space
# makes the pelvis snap 20-38 runtime pixels between adjacent keys.  These are
# authored upper-torso axes (source-cell coordinates), reviewed against the
# detailed source grids.  Registering the keys to them keeps the walk's body
# centred while the knees, feet, arms, and bag still perform their distinct
# illustrated motion.  They are roots, not interpolation offsets.
HERO_WALK_TORSO_ROOT_X: dict[str, tuple[float, ...]] = {
    "black_dave": (174.0, 174.0, 181.0, 155.0, 140.0, 124.0, 139.0, 160.0, 142.0, 126.0, 88.0, 105.0),
    "shelly": (161.0, 142.0, 142.0, 125.0, 113.0, 125.0, 159.0, 145.0, 141.0, 123.0, 108.0, 116.0),
}
SHELLY_EXTRA_SOURCES = {
    # Each source drawing gets a registered approach/settle in-between. The
    # paired keys are intentionally transformed by the 16-pose profiles above,
    # so they do not become identical atlas cells.
    "refill": (0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7),
    "pants": (8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13, 14, 14, 15, 15),
}
CHIEF_SOURCES = {
    "idle": (0, 1, 2, 3, 4, 3, 2, 1, 0, 2, 4, 1),
    "move": tuple(range(12)),
    "attack": (0, 5, 9, 10, 11, 12, 13, 0),
    "frenzy": (5, 7, 9, 10, 11, 12, 13, 14),
    "guard": (0, 1, 2, 3, 13, 4, 2, 0),
    "sit": tuple(range(16)),
    "pet": (0, 1, 2, 14, 14, 3, 1, 0),
    "command": (0, 4, 5, 7, 9, 10, 13, 0),
}
ENEMY_SOURCES = {
    "idle": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "spawn": (4, 4, 2, 1, 0, 0, 0, 0),
    "walk": (1, 1, 2, 2, 1, 2, 2, 1, 1, 2, 1, 2),
    "attack": (0, 1, 3, 3, 3, 2, 1, 0),
    "charge": (0, 1, 2, 3, 3, 2, 1, 0),
    "recovery": (3, 3, 2, 2, 1, 1, 0, 0),
    "hurt": (0, 2, 4, 4, 4, 2, 1, 0),
    "down": (0, 2, 4, 4, 4, 4, 4, 4),
}
COUCH_SOURCES = {
    "idle": (0, 1, 2, 3, 4, 3, 2, 1, 0, 2, 4, 1),
    "spawn": (9, 9, 6, 5, 0, 1, 2, 0),
    "walk": tuple(range(16)),
    "stick_attack": (0, 1, 5, 6, 7, 6, 5, 0),
    "stick_recovery": (7, 6, 5, 4, 3, 2, 1, 0),
    "pump_attack": (0, 1, 5, 6, 8, 6, 5, 0),
    "pump_recovery": (8, 6, 5, 4, 3, 2, 1, 0),
    "hurt": (0, 6, 9, 9, 9, 5, 1, 0),
    "down": (0, 0, 0, 0, 0, 0, 9, 9),
    "laugh": (0, 1, 2, 3, 4, 3, 2, 0),
}
JERRY_SOURCES = {
    "idle": (0, 1, 2, 3, 7, 3, 2, 1, 0, 2, 1, 7),
    "support": (0, 2, 7, 1, 3, 0, 2, 7, 3, 1, 2, 0),
    "talk": (0, 4, 5, 4, 5, 3, 2, 7, 4, 5, 3, 0),
    "point": (0, 5, 6, 6, 5, 4, 1, 0, 5, 6, 4, 1),
}


def _profile_for(actor: str, state: str) -> str:
    if state in _HERO_STABLE_ACTIONS:
        return "dave_combat_stable" if actor == "black_dave" else "hero_combat_stable"
    if actor == "chief" and state == "idle":
        return "chief_idle_extended"
    if actor == "chief" and state == "sit":
        return "chief_sit_extended"
    if actor in ENEMY_KINDS and state == "idle":
        return "enemy_idle_extended"
    if actor in ENEMY_KINDS and state == "walk":
        return "move_extended"
    if actor == "couch" and state == "idle":
        return "couch_idle_extended"
    if actor == "jerry" and state in JERRY_STATES:
        return "jerry_extended"
    if actor == "shelly" and state == "refill":
        return "refill_extended"
    if actor == "shelly" and state == "pants":
        return "pants_extended"
    if state in {"walk", "move"}:
        return "move"
    if state == "air_attack":
        return "air"
    if state == "guard":
        return "idle"
    if state.startswith("attack_") or state in {"heavy", "attack", "charge", "recovery", "stick_attack", "stick_recovery", "pump_attack", "pump_recovery"}:
        return "attack"
    if state in {"super", "frenzy"}:
        return "power"
    if state in JERRY_STATES or state == "ride":
        return state
    return state


def _split(path: Path, columns: int, rows: int) -> list[Image.Image]:
    atlas = Image.open(path).convert("RGBA")
    return [
        atlas.crop(
            (
                round(column * atlas.width / columns),
                round(row * atlas.height / rows),
                round((column + 1) * atlas.width / columns),
                round((row + 1) * atlas.height / rows),
            )
        )
        for row in range(rows)
        for column in range(columns)
    ]


def _split_direct_reference(path: Path, columns: int, rows: int) -> list[Image.Image]:
    """Load a transparent pose grid and reject filler or contaminated cells."""

    if not path.is_file():
        raise FileNotFoundError(f"missing direct animation reference: {path}")
    frames = _split(path, columns, rows)
    signatures: set[tuple[tuple[int, int], bytes]] = set()
    for index, frame in enumerate(frames):
        alpha = frame.getchannel("A")
        bounds = alpha.getbbox()
        if bounds is None:
            raise ValueError(f"{path.name} cell {index} is empty")
        if alpha.getextrema()[0] != 0:
            raise ValueError(f"{path.name} cell {index} lost its transparent background")
        cropped = frame.crop(bounds)
        signature = (cropped.size, cropped.tobytes())
        if signature in signatures:
            raise ValueError(f"{path.name} cell {index} repeats an earlier normalized drawing")
        signatures.add(signature)
        magenta = sum(
            alpha_value >= 8 and red >= 210 and blue >= 210 and green <= 90
            for red, green, blue, alpha_value in cropped.get_flattened_data()
        )
        if magenta:
            raise ValueError(f"{path.name} cell {index} retains {magenta} visible chroma-key pixels")
    return frames


def _strip_fit_transform(
    sources: list[Image.Image],
    indices: tuple[int, ...],
    cell_size: tuple[int, int],
    maximum_size: tuple[int, int] | None = None,
) -> PoseTransform:
    """Fit an illustrated strip once so anatomy cannot pulse between phases.

    Fitting every cropped drawing independently makes a crouched pose expand to
    the same height as an upright pose.  That changes the apparent size of the
    actor from frame to frame and reads as a wavy/warped gait.  A shared scale
    preserves the size differences authored inside the source strip.
    """

    if not indices:
        raise ValueError("cannot fit an empty animation strip")
    cell_width, cell_height = cell_size
    requested_width, requested_height = maximum_size or (cell_width - 2, cell_height - 2)
    maximum_width = max(1, min(cell_width - 2, requested_width))
    maximum_height = max(1, min(cell_height - 2, requested_height))
    visible_sizes: list[tuple[int, int]] = []
    for source_index in indices:
        bounds = sources[source_index].getchannel("A").getbbox()
        if bounds is None:
            raise ValueError(f"source pose {source_index} contains no visible pixels")
        visible_sizes.append((bounds[2] - bounds[0], bounds[3] - bounds[1]))
    scale = min(
        maximum_width / max(width for width, _height in visible_sizes),
        maximum_height / max(height for _width, height in visible_sizes),
    )
    return PoseTransform(scale_x=scale, scale_y=scale)


def _direct_reference_key(actor: str, state: str) -> str:
    return f"direct:{actor}:{state}"


def _split_jerry_reference(path: Path) -> list[Image.Image]:
    """Extract the eight detailed Jerry poses from the approved v2 sheet.

    The generated reference deliberately uses a near-black presentation
    backdrop.  A brightness/chroma matte followed by a small morphological
    close retains Jerry's black leather silhouette while removing the soft
    charcoal background; the large open spaces in his walker remain clear.
    """

    sheet = Image.open(path).convert("RGBA")
    columns, rows = 4, 2
    cell_width, cell_height = sheet.width // columns, sheet.height // rows
    frames: list[Image.Image] = []
    for row in range(rows):
        for column in range(columns):
            frame = sheet.crop(
                (
                    column * cell_width,
                    row * cell_height,
                    (column + 1) * cell_width,
                    (row + 1) * cell_height,
                )
            )
            matte = Image.new("L", frame.size)
            matte.putdata(
                [
                    255
                    if max(red, green, blue) - min(red, green, blue) > 8
                    or (red + green + blue) / 3 > 45
                    else 0
                    for red, green, blue, _alpha in frame.get_flattened_data()
                ]
            )
            matte = matte.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(5))
            bounds = matte.getbbox()
            if bounds is None:
                raise ValueError(f"Jerry reference pose {len(frames)} contains no extractable art")
            # The leather is intentionally near-black.  A brightness/chroma
            # matte can therefore punch transparent holes through the coat.
            # Only transparency connected to the cell edge is background;
            # enclosed transparent islands are dark material and must remain.
            matte = _fill_enclosed_alpha_holes(matte)
            frame.putalpha(matte)
            frames.append(frame.crop(bounds))
    return frames


def _fill_enclosed_alpha_holes(alpha: Image.Image) -> Image.Image:
    """Make enclosed matte holes opaque while retaining exterior transparency."""

    width, height = alpha.size
    values = list(alpha.get_flattened_data())
    visited = bytearray(width * height)
    stack: list[tuple[int, int]] = []
    for x in range(width):
        stack.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        stack.extend(((0, y), (width - 1, y)))
    while stack:
        x, y = stack.pop()
        index = y * width + x
        if visited[index] or values[index] >= 8:
            continue
        visited[index] = 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                stack.append((nx, ny))
    for index, value in enumerate(values):
        if value < 8 and not visited[index]:
            values[index] = 255
    result = Image.new("L", alpha.size)
    result.putdata(values)
    return result


def _sprite_crop(source: Image.Image) -> Image.Image:
    bounds = source.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("sprite source contains no visible pixels")
    return source.crop(bounds)


def _remove_tiny_alpha_components(source: Image.Image, minimum_pixels: int = 6) -> Image.Image:
    """Drop detached matte specks without touching connected sprite/effect art."""

    result = source.copy()
    alpha = result.getchannel("A")
    width, height = alpha.size
    pixels = list(alpha.get_flattened_data())
    visited = bytearray(width * height)
    removed: list[int] = []
    for start, value in enumerate(pixels):
        if value < 8 or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            x, y = current % width, current // width
            for neighbor_x, neighbor_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if not (0 <= neighbor_x < width and 0 <= neighbor_y < height):
                    continue
                neighbor = neighbor_y * width + neighbor_x
                if not visited[neighbor] and pixels[neighbor] >= 8:
                    visited[neighbor] = 1
                    stack.append(neighbor)
        if len(component) < minimum_pixels:
            removed.extend(component)
    if removed:
        for index in removed:
            pixels[index] = 0
        cleaned_alpha = Image.new("L", alpha.size)
        cleaned_alpha.putdata(pixels)
        result.putalpha(cleaned_alpha)
    return result


def _remove_distant_walk_ghosts(source: Image.Image) -> Image.Image:
    """Remove only small, isolated walk-sheet render spills.

    Two Dave reference cells contain a detached shoe-sized fragment at the
    opposite edge of the source cell.  It is not connected to the illustrated
    body, sits well outside its bounds, and survives a generic tiny-speck pass.
    Keeping it makes a bright blue phantom flicker at the edge of the walk.
    This deliberately leaves nearby disconnected details (glasses, jewelry,
    loose hair) alone: a component must be both distant and below 1.2% of the
    primary body area before it is removed.
    """

    result = source.copy()
    alpha = result.getchannel("A")
    width, height = alpha.size
    pixels = list(alpha.get_flattened_data())
    visited = bytearray(width * height)
    components: list[tuple[list[int], tuple[int, int, int, int]]] = []
    for start, value in enumerate(pixels):
        if value < 8 or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        component: list[int] = []
        left = right = start % width
        top = bottom = start // width
        while stack:
            current = stack.pop()
            component.append(current)
            x, y = current % width, current // width
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for neighbor_x, neighbor_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if not (0 <= neighbor_x < width and 0 <= neighbor_y < height):
                    continue
                neighbor = neighbor_y * width + neighbor_x
                if not visited[neighbor] and pixels[neighbor] >= 8:
                    visited[neighbor] = 1
                    stack.append(neighbor)
        components.append((component, (left, top, right + 1, bottom + 1)))
    if len(components) < 2:
        return result
    primary, primary_bounds = max(components, key=lambda entry: len(entry[0]))
    primary_area = len(primary)
    maximum_ghost_pixels = max(12, math.ceil(primary_area * 0.012))
    removed: list[int] = []
    for component, bounds in components:
        if component is primary or len(component) > maximum_ghost_pixels:
            continue
        horizontal_gap = max(primary_bounds[0] - bounds[2], bounds[0] - primary_bounds[2], 0)
        vertical_gap = max(primary_bounds[1] - bounds[3], bounds[1] - primary_bounds[3], 0)
        if horizontal_gap > 10 or vertical_gap > 10:
            removed.extend(component)
    if removed:
        for index in removed:
            pixels[index] = 0
        cleaned_alpha = Image.new("L", alpha.size)
        cleaned_alpha.putdata(pixels)
        result.putalpha(cleaned_alpha)
    return result


def _paste_scaled(
    canvas: Image.Image,
    source: Image.Image,
    *,
    x: int,
    bottom: int,
    scale: float,
    angle: float = 0.0,
) -> None:
    sprite = _sprite_crop(source)
    sprite = sprite.resize(
        (max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))),
        Image.Resampling.NEAREST,
    )
    if angle:
        sprite = sprite.rotate(-angle, resample=Image.Resampling.NEAREST, expand=True)
    canvas.alpha_composite(sprite, (x, bottom - sprite.height))


def _draw_bmx(canvas: Image.Image, crank_phase: int) -> None:
    """Paint a compact, outlined BMX with rims, spokes, frame and drivetrain."""

    draw = ImageDraw.Draw(canvas)
    rear, front, radius = (61, 115), (128, 115), 21
    for center in (rear, front):
        cx, cy = center
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(9, 13, 21, 255), width=5)
        draw.ellipse((cx - radius + 3, cy - radius + 3, cx + radius - 3, cy + radius - 3), outline=(175, 190, 204, 255), width=2)
        draw.arc((cx - radius + 4, cy - radius + 4, cx + radius - 4, cy + radius - 4), 205, 325, fill=(231, 238, 242, 255), width=1)
        for spoke in range(8):
            angle = math.tau * spoke / 8 + crank_phase * math.tau / 64
            sx = cx + round(math.cos(angle) * (radius - 5))
            sy = cy + round(math.sin(angle) * (radius - 5))
            draw.line((cx, cy, sx, sy), fill=(104, 121, 137, 255), width=1)
        draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=(229, 180, 65, 255), outline=(39, 29, 21, 255))

    seat, crank, head = (86, 84), (96, 113), (121, 83)
    frame_segments = (
        (rear, seat), (seat, crank), (crank, rear), (seat, head),
        (head, crank), (crank, front), (head, front),
    )
    for start, end in frame_segments:
        draw.line((*start, *end), fill=(10, 21, 35, 255), width=6)
    for start, end in frame_segments:
        draw.line((*start, *end), fill=(24, 113, 197, 255), width=3)
    draw.line((*seat, *head), fill=(79, 181, 241, 255), width=1)
    draw.line((84, 83, 94, 83), fill=(16, 18, 24, 255), width=5)
    draw.line((85, 82, 94, 82), fill=(86, 91, 101, 255), width=1)
    draw.line((121, 83, 124, 70, 132, 68), fill=(11, 18, 28, 255), width=5, joint="curve")
    draw.line((121, 82, 124, 70, 132, 68), fill=(167, 185, 198, 255), width=2, joint="curve")
    draw.line((129, 66, 136, 69), fill=(20, 24, 31, 255), width=3)
    draw.line((122, 75, 128, 73, 134, 74), fill=(56, 67, 80, 255), width=1)

    crank_angle = math.tau * crank_phase / 8
    px = crank[0] + round(math.cos(crank_angle) * 10)
    py = crank[1] + round(math.sin(crank_angle) * 10)
    opposite_x = crank[0] - (px - crank[0])
    opposite_y = crank[1] - (py - crank[1])
    draw.ellipse((crank[0] - 4, crank[1] - 4, crank[0] + 4, crank[1] + 4), outline=(224, 177, 58, 255), width=2)
    draw.line((*crank, px, py), fill=(224, 177, 58, 255), width=2)
    draw.line((*crank, opposite_x, opposite_y), fill=(224, 177, 58, 255), width=2)
    draw.line((px - 3, py, px + 3, py), fill=(24, 27, 32, 255), width=2)
    draw.line((opposite_x - 3, opposite_y, opposite_x + 3, opposite_y), fill=(24, 27, 32, 255), width=2)
    draw.line((*rear, *crank), fill=(206, 166, 65, 255), width=1)


def _build_sunset_sources(
    dave_frames: list[Image.Image],
    shelly_frames: list[Image.Image],
    chief_frames: list[Image.Image],
) -> list[Image.Image]:
    """Compose eight detailed, reusable group cels for the post-Couch ride."""

    dave_keys = (5, 6, 7, 8, 9, 8, 3, 6)
    shelly_keys = (5, 6, 7, 8, 9, 8, 4, 6)
    chief_keys = (5, 6, 7, 8, 9, 8, 1, 6)
    frames: list[Image.Image] = []
    for phase, (dave_key, shelly_key, chief_key) in enumerate(zip(dave_keys, shelly_keys, chief_keys)):
        cel = Image.new("RGBA", (256, 144), (0, 0, 0, 0))
        _draw_bmx(cel, phase)
        # Dave is deliberately lower and slightly forward over the BMX; his
        # alternating detailed walk keys read as pedalling rather than the old
        # rectangle placeholder.  Phase six uses his glasses/hat gesture as a
        # small farewell beat while the group keeps moving.
        _paste_scaled(
            cel,
            dave_frames[dave_key],
            x=69 + (phase % 2),
            bottom=119 - (1 if phase in {1, 3, 5, 7} else 0),
            scale=0.66,
            angle=-2.0 if phase in {1, 2} else 0.0,
        )
        _paste_scaled(
            cel,
            shelly_frames[shelly_key],
            x=155 + (phase % 3),
            bottom=132 - (1 if phase in {1, 4, 7} else 0),
            scale=0.61,
        )
        _paste_scaled(
            cel,
            chief_frames[chief_key],
            x=202 - (phase % 2),
            bottom=134 - (1 if phase in {2, 5} else 0),
            scale=0.43,
        )
        frames.append(cel)
    return frames


def _canonicalize(frames: list[Image.Image], preserved: set[int]) -> list[Image.Image]:
    transpose = getattr(Image, "Transpose", Image).FLIP_LEFT_RIGHT
    return [frame if index in preserved else frame.transpose(transpose) for index, frame in enumerate(frames)]


SHELLY_MICROTORCH_ANCHORS: tuple[tuple[int, int], ...] = (
    (90, 42), (90, 42), (80, 38), (96, 43), (96, 60),
    (94, 47), (94, 47), (94, 47), (94, 47), (94, 47),
    (95, 42), (108, 42), (109, 50), (91, 28), (108, 42),
    (47, 29), (105, 46), (53, 49), (80, 35), (57, 43),
)
SHELLY_REFILL_TORCH_ANCHORS: tuple[tuple[int, int], ...] = (
    (94, 41), (94, 41), (79, 38), (94, 43),
    (94, 43), (94, 43), (94, 43), (94, 43),
)


def _add_shelly_microtorch(source: Image.Image, anchor: tuple[int, int]) -> Image.Image:
    """Replace the old grenade-like hand prop with a compact R-shaped torch."""

    frame = source.copy()
    draw = ImageDraw.Draw(frame)
    x, y = anchor
    outline = (31, 27, 31, 255)
    metal_dark = (54, 65, 70, 255)
    metal = (117, 139, 141, 255)
    metal_light = (202, 218, 205, 255)
    cyan = (63, 183, 193, 255)
    silhouette = [
        (x - 4, y + 2), (x - 4, y - 12), (x - 1, y - 16),
        (x + 3, y - 16), (x + 5, y - 13), (x + 5, y - 9),
        (x + 3, y - 7), (x + 6, y - 3), (x + 6, y + 2),
    ]
    draw.polygon(silhouette, fill=outline)
    draw.rectangle((x - 2, y - 10, x + 2, y), fill=metal_dark)
    draw.rectangle((x - 1, y - 9, x + 1, y - 1), fill=metal)
    draw.rectangle((x - 1, y - 7, x + 1, y - 5), fill=cyan)
    draw.line((x + 1, y - 14, x + 5, y - 18), fill=outline, width=3)
    draw.line((x + 2, y - 15, x + 5, y - 18), fill=metal_light, width=1)
    draw.line((x + 3, y - 6, x + 5, y - 3), fill=metal_light, width=1)
    return frame


def _render_pose(
    source: Image.Image,
    transform: PoseTransform,
    cell_size: tuple[int, int],
    maximum_size: tuple[int, int] | None = None,
    *,
    source_root_x: float | None = None,
    landmarks: tuple[tuple[int, int], ...] = (),
    landmark_sink: list[tuple[int, int]] | None = None,
) -> Image.Image:
    cell_width, cell_height = cell_size
    bbox = source.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("source pose contains no visible pixels")
    sprite = source.crop(bbox)
    # The source cell's horizontal centre is normally the authored pelvis/root
    # axis.  The illustrated hero walk strips are the exception: those concept
    # cells include forward translation, while runtime actors already advance
    # in world space.  A per-key torso root removes that duplicated translation
    # without altering, blending, or inventing any source drawing.
    root_axis_x = source.width * 0.5 if source_root_x is None else float(source_root_x)
    root_x = root_axis_x - bbox[0]
    root_y = float(bbox[3] - bbox[1])
    landmark_points = [
        (float(point_x - bbox[0]), float(point_y - bbox[1]))
        for point_x, point_y in landmarks
    ]
    width = max(1, round(sprite.width * transform.scale_x))
    height = max(1, round(sprite.height * transform.scale_y))
    root_x *= width / sprite.width
    root_y *= height / sprite.height
    landmark_points = [
        (point_x * width / sprite.width, point_y * height / sprite.height)
        for point_x, point_y in landmark_points
    ]
    sprite = sprite.resize((width, height), Image.Resampling.NEAREST)
    if transform.angle:
        # Transform a private marker with the sprite so rotation cannot make
        # the actor orbit around a changing cropped-bounds centre.
        marker = Image.new("L", sprite.size, 0)
        marker_x = max(0, min(sprite.width - 1, round(root_x - 0.5)))
        marker_y = max(0, min(sprite.height - 1, round(root_y - 1.0)))
        marker_draw = ImageDraw.Draw(marker)
        marker_draw.rectangle(
            (
                max(0, marker_x - 1),
                max(0, marker_y - 2),
                min(sprite.width - 1, marker_x + 1),
                marker_y,
            ),
            fill=255,
        )
        landmark_markers: list[Image.Image] = []
        for point_x, point_y in landmark_points:
            landmark_marker = Image.new("L", sprite.size, 0)
            marker_draw = ImageDraw.Draw(landmark_marker)
            marker_x = max(0, min(sprite.width - 1, round(point_x)))
            marker_y = max(0, min(sprite.height - 1, round(point_y)))
            marker_draw.rectangle(
                (
                    max(0, marker_x - 1),
                    max(0, marker_y - 1),
                    min(sprite.width - 1, marker_x + 1),
                    min(sprite.height - 1, marker_y + 1),
                ),
                fill=255,
            )
            landmark_markers.append(landmark_marker)
        sprite = sprite.rotate(-transform.angle, resample=Image.Resampling.NEAREST, expand=True)
        marker = marker.rotate(-transform.angle, resample=Image.Resampling.NEAREST, expand=True)
        landmark_markers = [
            landmark_marker.rotate(-transform.angle, resample=Image.Resampling.NEAREST, expand=True)
            for landmark_marker in landmark_markers
        ]
        marker_bbox = marker.getbbox()
        if marker_bbox is None:
            raise ValueError("pose root marker was lost during rotation")
        root_x = (marker_bbox[0] + marker_bbox[2]) * 0.5
        root_y = float(marker_bbox[3])
        landmark_points = []
        for landmark_marker in landmark_markers:
            landmark_bbox = landmark_marker.getbbox()
            if landmark_bbox is None:
                raise ValueError("pose hand landmark was lost during rotation")
            landmark_points.append(
                (
                    (landmark_bbox[0] + landmark_bbox[2] - 1) * 0.5,
                    (landmark_bbox[1] + landmark_bbox[3] - 1) * 0.5,
                )
            )
    # Pillow's expanded rotation canvas contains transparent corner rows.
    # Trim them before bottom anchoring so the *visible* feet/wheels/walker,
    # rather than the invisible canvas, stay on the shared ground line.
    rotated_bbox = sprite.getchannel("A").getbbox()
    if rotated_bbox is None:
        raise ValueError("transformed pose contains no visible pixels")
    sprite = sprite.crop(rotated_bbox)
    landmark_points = [
        (point_x - rotated_bbox[0], point_y - rotated_bbox[1])
        for point_x, point_y in landmark_points
    ]
    if transform.angle:
        root_x -= rotated_bbox[0]
        root_y -= rotated_bbox[1]
    # Keep every phase inside its cell while retaining the authored bottom/foot
    # anchor.  Rotation and anisotropic scale change the silhouette; offsets
    # only place that changed pose in the frame.
    requested_width, requested_height = maximum_size or (cell_width - 2, cell_height - 2)
    maximum_width = max(1, min(cell_width - 2, requested_width))
    maximum_height = max(1, min(cell_height - 2, requested_height))
    if sprite.width > maximum_width or sprite.height > maximum_height:
        fit = min(maximum_width / sprite.width, maximum_height / sprite.height)
        resized_width = max(1, round(sprite.width * fit))
        resized_height = max(1, round(sprite.height * fit))
        root_x *= resized_width / sprite.width
        root_y *= resized_height / sprite.height
        landmark_points = [
            (
                point_x * resized_width / sprite.width,
                point_y * resized_height / sprite.height,
            )
            for point_x, point_y in landmark_points
        ]
        sprite = sprite.resize(
            (resized_width, resized_height),
            Image.Resampling.NEAREST,
        )
    result = Image.new("RGBA", cell_size, (0, 0, 0, 0))
    x = round(cell_width * 0.5 - root_x) + transform.offset_x
    # Vertical registration uses the transformed visible sole/ground edge.
    # Rotation may move the tracked pelvis relative to the lowest foot pixel,
    # but it must never make a grounded actor hop between adjacent poses.
    y = cell_height - sprite.height - 2 + transform.offset_y
    x = max(0, min(cell_width - sprite.width, x))
    y = max(0, min(cell_height - sprite.height, y))
    result.alpha_composite(sprite, (x, y))
    if landmark_sink is not None:
        landmark_sink.extend(
            (
                max(0, min(cell_width - 1, round(point_x + x))),
                max(0, min(cell_height - 1, round(point_y + y))),
            )
            for point_x, point_y in landmark_points
        )
    return result


_BREATH_SHAPES = (
    (0, 0, 0),
    (1, 0, 0),
    (2, 0, 0),
    (2, 1, 0),
    (3, 1, 0),
    (2, 2, 0),
    (1, 1, 1),
    (0, 1, 1),
    (-1, 0, 1),
    (-1, -1, 0),
    (0, -1, -1),
    (1, -1, -1),
)


def _render_breath_pose(
    source: Image.Image,
    phase: int,
    cell_size: tuple[int, int],
    *,
    landmarks: tuple[tuple[int, int], ...] = (),
    landmark_sink: list[tuple[int, int]] | None = None,
) -> Image.Image:
    """Deform only the upper body so breathing never makes planted feet slide."""

    bounds = source.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("breathing source contains no visible pixels")
    sprite = source.crop(bounds)
    root_x = source.width * 0.5 - bounds[0]
    split = max(2, min(sprite.height - 2, round(sprite.height * 0.58)))
    overlap = 3
    upper_bottom = min(sprite.height, split + overlap)
    lower_top = max(0, split - overlap)
    upper = sprite.crop((0, 0, sprite.width, upper_bottom))
    lower = sprite.crop((0, lower_top, sprite.width, sprite.height))
    upper_source_size = upper.size
    height_delta, width_delta, shoulder_shift = _BREATH_SHAPES[phase]
    upper = upper.resize(
        (
            max(1, upper.width + width_delta),
            max(1, upper.height + height_delta),
        ),
        Image.Resampling.NEAREST,
    )
    result = Image.new("RGBA", cell_size, (0, 0, 0, 0))
    cell_width, cell_height = cell_size
    lower_x = round(cell_width * 0.5 - root_x)
    lower_y = cell_height - lower.height - 2
    result.alpha_composite(lower, (lower_x, lower_y))
    upper_x = round(cell_width * 0.5 - root_x) + shoulder_shift
    upper_y = lower_y + overlap * 2 - upper.height
    result.alpha_composite(upper, (upper_x, upper_y))
    if landmark_sink is not None:
        for point_x, point_y in landmarks:
            local_x = point_x - bounds[0]
            local_y = point_y - bounds[1]
            if local_y <= split:
                rendered_x = upper_x + local_x * upper.width / upper_source_size[0]
                rendered_y = upper_y + local_y * upper.height / upper_source_size[1]
            else:
                rendered_x = lower_x + local_x
                rendered_y = lower_y + local_y - lower_top
            landmark_sink.append(
                (
                    max(0, min(cell_width - 1, round(rendered_x))),
                    max(0, min(cell_height - 1, round(rendered_y))),
                )
            )
    return result


def _sources_for(
    actor: str,
    state: str,
    source_sets: dict[str, list[Image.Image]],
) -> tuple[list[Image.Image], tuple[int, ...]]:
    direct_key = _direct_reference_key(actor, state)
    if direct_key in source_sets:
        sources = source_sets[direct_key]
        return sources, tuple(range(len(sources)))
    if actor in {"black_dave", "shelly"}:
        if state == "walk":
            return source_sets[f"{actor}_walk"], HERO_SOURCES[state]
        if actor == "shelly" and state in {"refill", "pants"}:
            return source_sets["shelly_extras"], SHELLY_EXTRA_SOURCES[state]
        return source_sets[actor], HERO_SOURCES[state]
    if actor == "chief":
        return source_sets["chief"], CHIEF_SOURCES[state]
    if actor in ENEMY_KINDS:
        row = ENEMY_KINDS.index(actor)
        local_indices = ENEMY_SOURCES[state]
        if state == "down" and actor in {"cart", "pipe"}:
            # These two rows already have a horizontal final key.  Fall from
            # the upright key, then settle into that purpose-drawn prone cell.
            local_indices = (0, 0, 0, 0, 0, 0, 4, 4)
        return source_sets["enemies"], tuple(row * 5 + index for index in local_indices)
    if actor == "couch":
        return source_sets["couch"], COUCH_SOURCES[state]
    if actor == "jerry":
        return source_sets["jerry"], JERRY_SOURCES[state]
    if actor == "victory":
        return source_sets["victory"], (0, 1, 2, 3, 2, 1, 3, 0)
    if actor == "sunset":
        return source_sets["sunset"], tuple(range(BASE_POSES_PER_CLIP))
    raise KeyError(f"No animation source mapping for {actor}:{state}")


def _make_atlases(output_root: Path) -> dict[tuple[str, str], list[Image.Image]]:
    sprite_root = PROJECT_ROOT / "assets" / "sprites"
    source_sets: dict[str, list[Image.Image]] = {
        "black_dave": _split(sprite_root / "black_dave_atlas.png", 5, 4),
        "shelly": [
            _add_shelly_microtorch(frame, SHELLY_MICROTORCH_ANCHORS[index])
            for index, frame in enumerate(_split(sprite_root / "shelly_atlas.png", 5, 4))
        ],
        "black_dave_walk": [
            _remove_distant_walk_ghosts(frame)
            for frame in _split(PROJECT_ROOT / "assets" / "reference" / "black_dave_walk_reference_v2.png", 6, 2)
        ],
        "shelly_walk": [
            _remove_distant_walk_ghosts(frame)
            for frame in _split(PROJECT_ROOT / "assets" / "reference" / "shelly_walk_reference_v2.png", 6, 2)
        ],
        "shelly_extras": [
            _add_shelly_microtorch(frame, SHELLY_REFILL_TORCH_ANCHORS[index])
            if index < len(SHELLY_REFILL_TORCH_ANCHORS) else frame
            for index, frame in enumerate(_split(sprite_root / "shelly_idle_extended.png", 8, 2))
        ],
        "chief": _split(sprite_root / "chief_atlas.png", 5, 3),
        "enemies": _canonicalize(_split(sprite_root / "enemies_atlas.png", 5, 4), {8, 18}),
        "couch": [
            _remove_tiny_alpha_components(frame)
            for frame in _canonicalize(_split(sprite_root / "couch_denim_v2_atlas.png", 5, 2), {6, 7})
        ],
        "jerry": _split_jerry_reference(PROJECT_ROOT / "assets" / "reference" / "jerry_pose_reference_v2.png"),
        "victory": _split(sprite_root / "victory_hug_treats.png", 4, 1),
    }
    reference_root = PROJECT_ROOT / "assets" / "reference"
    for (actor, state), (filename, columns, rows) in DIRECT_REFERENCE_SPECS.items():
        source_sets[_direct_reference_key(actor, state)] = _split_direct_reference(
            reference_root / filename,
            columns,
            rows,
        )
    source_sets["sunset"] = _build_sunset_sources(
        source_sets["black_dave"],
        source_sets["shelly"],
        source_sets["chief"],
    )
    rendered: dict[tuple[str, str], list[Image.Image]] = {}
    dave_fist_metadata: dict[str, list[dict[str, object]]] = {}
    atlas_groups: dict[str, list] = {}
    for clip in ANIMATION_CLIPS:
        atlas_groups.setdefault(clip.atlas, []).append(clip)

    for relative, clips in atlas_groups.items():
        row_count = max(clip.row for clip in clips) + 1
        atlas_columns = max(clip.frame_count for clip in clips)
        atlas = Image.new(
            "RGBA",
            (atlas_columns * clips[0].cell_width, row_count * clips[0].cell_height),
            (0, 0, 0, 0),
        )
        for clip in clips:
            sources, indices = _sources_for(clip.actor, clip.state, source_sets)
            base_frame_count = len(indices)
            if clip.frame_count != base_frame_count:
                raise ValueError(
                    f"{clip.actor}:{clip.state} must expose its {base_frame_count} authored source phases; "
                    f"manifest provides {clip.frame_count} runtime phases"
                )
            key_poses: list[Image.Image] = []
            phase_fist_anchors: list[dict[str, object]] = []

            def render_landmarks(source_index: int) -> tuple[tuple[int, int], ...]:
                if clip.actor != "black_dave":
                    return ()
                if clip.state == "walk":
                    return DAVE_WALK_FIST_LANDMARKS[source_index]
                return DAVE_COMBAT_FIST_LANDMARKS[source_index]

            def record_landmarks(source_index: int, sink: list[tuple[int, int]]) -> None:
                if clip.actor != "black_dave":
                    return
                if len(sink) != 2:
                    raise ValueError(
                        f"{clip.actor}:{clip.state} source {source_index} produced {len(sink)} fist landmarks"
                    )
                phase_fist_anchors.append(
                    {
                        "source": source_index,
                        "rear": list(sink[0]),
                        "lead": list(sink[1]),
                    }
                )

            if clip.actor in {"black_dave", "shelly"} and clip.state == "idle":
                for phase, source_index in enumerate(indices):
                    sink: list[tuple[int, int]] = []
                    key_poses.append(
                        _render_breath_pose(
                            sources[source_index],
                            phase,
                            (clip.cell_width, clip.cell_height),
                            landmarks=render_landmarks(source_index),
                            landmark_sink=sink if clip.actor == "black_dave" else None,
                        )
                    )
                    record_landmarks(source_index, sink)
            elif (
                clip.actor in {"black_dave", "shelly"} and clip.state == "walk"
            ) or (clip.actor, clip.state) in DIRECT_REFERENCE_SPECS:
                # These are separately illustrated keys. Keeping each cell
                # single-source prevents split-compositing from duplicating
                # anatomy or leaving prop/effect ghosts between gait phases.
                strip_transform = _strip_fit_transform(
                    sources,
                    indices,
                    (clip.cell_width, clip.cell_height),
                    DIRECT_RENDER_LIMITS.get((clip.actor, clip.state)),
                )
                for source_index in indices:
                    sink = []
                    source_root_x = None
                    if clip.actor in {"black_dave", "shelly"} and clip.state == "walk":
                        source_root_x = HERO_WALK_TORSO_ROOT_X[clip.actor][source_index]
                    key_poses.append(
                        _render_pose(
                            sources[source_index],
                            strip_transform,
                            (clip.cell_width, clip.cell_height),
                            DIRECT_RENDER_LIMITS.get((clip.actor, clip.state)),
                            source_root_x=source_root_x,
                            landmarks=render_landmarks(source_index),
                            landmark_sink=sink if clip.actor == "black_dave" else None,
                        )
                    )
                    record_landmarks(source_index, sink)
            else:
                profile = PROFILES[_profile_for(clip.actor, clip.state) if clip.actor != "victory" else "victory"]
                if len(profile) != base_frame_count:
                    raise ValueError(
                        f"{clip.actor}:{clip.state} has {len(profile)} transforms for {base_frame_count} source phases"
                    )
                if profile[-1] == profile[0]:
                    # The return-to-ready phase is a settled follow-through, not a
                    # byte-for-byte copy of the opening guard/stance.
                    profile = (*profile[:-1], PoseTransform(0.9, 1.01, 0.99, 1, 0))
                if clip.state == "down" and clip.actor in {"cart", "pipe", "couch"}:
                    # A horizontal source key must not be rotated a second time.
                    profile = (*profile[:6], PoseTransform(-1, 1.02, 0.98, -1, 1), PoseTransform(0.8, 1.01, 0.99, 1, 0))
                for phase, source_index in enumerate(indices):
                    sink = []
                    key_poses.append(
                        _render_pose(
                            sources[source_index],
                            profile[phase],
                            (clip.cell_width, clip.cell_height),
                            landmarks=render_landmarks(source_index),
                            landmark_sink=sink if clip.actor == "black_dave" else None,
                        )
                    )
                    record_landmarks(source_index, sink)
            poses = key_poses
            if len(poses) != clip.frame_count:
                raise ValueError(
                    f"{clip.actor}:{clip.state} produced {len(poses)} cels for {clip.frame_count} manifest phases"
                )
            rendered[(clip.actor, clip.state)] = poses
            if clip.actor == "black_dave":
                if len(phase_fist_anchors) != clip.frame_count:
                    raise ValueError(f"{clip.state} fist landmark metadata is incomplete")
                dave_fist_metadata[clip.state] = phase_fist_anchors
            for phase, pose in enumerate(poses):
                atlas.alpha_composite(pose, (phase * clip.cell_width, clip.row * clip.cell_height))
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        atlas.save(destination, optimize=True)
        print(
            f"Wrote {destination.relative_to(output_root)}: "
            f"{len(clips)} clips / {sum(clip.frame_count for clip in clips)} poses"
        )
    metadata_destination = output_root / "assets" / "sprites" / "black_dave_fist_anchors.json"
    metadata_destination.parent.mkdir(parents=True, exist_ok=True)
    metadata_destination.write_text(
        json.dumps(
            {
                "version": 1,
                "cell_size": [128, 128],
                "states": dave_fist_metadata,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {metadata_destination.relative_to(output_root)}: {sum(len(phases) for phases in dave_fist_metadata.values())} pose landmarks")
    return rendered


def _contact_sheet(rendered: dict[tuple[str, str], list[Image.Image]], destination: Path) -> None:
    clips = list(ANIMATION_CLIPS)
    columns = 4
    rows = (len(clips) + columns - 1) // columns
    block_width, block_height = 680, 62
    sheet = Image.new("RGB", (columns * block_width, 42 + rows * block_height), (19, 22, 29))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((12, 11), f"THE FADES OF FATE - ANIMATION FLOOR QA - {total_authored_poses()} RUNTIME POSES", fill=(245, 220, 120), font=font)
    draw.text((12, 25), "Every cel is a rooted authored key; 30 Hz selection survives 30/60 FPS presentation without skipped in-betweens.", fill=(194, 205, 220), font=font)
    for index, clip in enumerate(clips):
        column, row = index // rows, index % rows
        x0, y0 = column * block_width + 8, 42 + row * block_height
        draw.text((x0, y0 + 2), f"{clip.actor}: {clip.state}", fill=(236, 239, 244), font=font)
        poses = rendered[(clip.actor, clip.state)]
        available_width = block_width - 104
        phase_width = max(12, available_width // max(1, len(poses)))
        thumb_size = max(10, min(42, phase_width - 2))
        for phase, pose in enumerate(poses):
            thumb = pose.copy()
            thumb.thumbnail((thumb_size, thumb_size), Image.Resampling.NEAREST)
            x = x0 + 92 + phase * phase_width
            checker = Image.new("RGBA", (thumb_size + 2, thumb_size + 2), (47, 53, 66, 255))
            ImageDraw.Draw(checker).rectangle((0, (thumb_size + 2) // 2, thumb_size + 1, thumb_size + 1), fill=(55, 62, 76, 255))
            checker.alpha_composite(thumb, ((checker.width - thumb.width) // 2, checker.height - thumb.height))
            sheet.paste(checker.convert("RGB"), (x, y0 + 13))
        draw.line((x0, y0 + block_height - 2, x0 + block_width - 12, y0 + block_height - 2), fill=(43, 48, 59))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, optimize=True)
    print(f"Wrote {destination.relative_to(PROJECT_ROOT)}")


def _walk_root_cadence_sheet(rendered: dict[tuple[str, str], list[Image.Image]], destination: Path) -> None:
    """Save a full-cell root/ground-line strip for locomotion regression QA."""

    # Expand the enemy rows explicitly so every locomotion family shares the
    # same full-cell registration view.
    entries = (
        ("black_dave", "walk"),
        ("shelly", "walk"),
        ("chief", "move"),
        *((kind, "walk") for kind in ENEMY_KINDS),
        ("couch", "walk"),
    )
    slot_width, slot_height = 164, 136
    label_width, header_height = 112, 36
    widest = max(len(rendered[entry]) for entry in entries)
    sheet = Image.new(
        "RGB",
        (label_width + widest * slot_width + 10, header_height + len(entries) * slot_height + 8),
        (18, 21, 28),
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((10, 8), "WALK ROOT / CADENCE QA", fill=(245, 220, 120), font=font)
    draw.text(
        (10, 21),
        "green = registered body axis; gold = shared foot line; every cel is an authored source key",
        fill=(194, 205, 220),
        font=font,
    )
    for row, (actor, state) in enumerate(entries):
        clip = next(candidate for candidate in ANIMATION_CLIPS if candidate.actor == actor and candidate.state == state)
        y0 = header_height + row * slot_height
        draw.text((8, y0 + 57), f"{actor}\n{state}", fill=(236, 239, 244), font=font)
        for phase, pose in enumerate(rendered[(actor, state)]):
            x0 = label_width + phase * slot_width
            # Keep a full cell visible: a cropped thumbnail hides root drift and
            # makes a planted foot look stable even when its registration moved.
            checker = Image.new("RGBA", (slot_width - 4, slot_height - 6), (46, 53, 66, 255))
            checker_draw = ImageDraw.Draw(checker)
            for stripe in range(0, checker.height, 8):
                checker_draw.rectangle((0, stripe, checker.width, stripe + 3), fill=(54, 61, 75, 255))
            origin_x = (checker.width - pose.width) // 2
            origin_y = checker.height - 4 - (pose.height - 2)
            checker_draw.line(
                (origin_x + clip.cell_width // 2, 2, origin_x + clip.cell_width // 2, checker.height - 4),
                fill=(75, 230, 156, 255),
                width=1,
            )
            checker_draw.line((0, checker.height - 4, checker.width, checker.height - 4), fill=(245, 195, 70, 255), width=1)
            checker.alpha_composite(pose, (origin_x, origin_y))
            sheet.paste(checker.convert("RGB"), (x0, y0 + 3))
            draw.text((x0 + 2, y0 + 123), f"{phase:02d}", fill=(166, 177, 193), font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, optimize=True)
    print(f"Wrote {destination.relative_to(PROJECT_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--qa-output", type=Path, default=PROJECT_ROOT / "build" / "animation_floor_qa.png")
    parser.add_argument(
        "--walk-qa-output",
        type=Path,
        default=PROJECT_ROOT / "build" / "walk_root_cadence_qa.png",
    )
    args = parser.parse_args()
    rendered = _make_atlases(args.output_root.resolve())
    _contact_sheet(rendered, args.qa_output.resolve())
    _walk_root_cadence_sheet(rendered, args.walk_qa_output.resolve())
    print(f"Animation floor complete: {len(ANIMATION_CLIPS)} clips, {total_authored_poses()} authored poses")


if __name__ == "__main__":
    main()
