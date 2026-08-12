from __future__ import annotations

"""Shared helpers for composing enemy variants from one runtime archetype."""

from typing import Any, Mapping, Sequence


_STAT_MULTIPLIER_FIELDS = (
    "health",
    "damage",
    "speed",
    "attack_range",
    "depth_range",
    "windup",
    "active",
    "recovery",
    "cooldown",
    "score",
    "token_cost",
    "ranged_attack_range",
    "ranged_depth_range",
    "ranged_windup",
    "ranged_active",
    "ranged_recovery",
    "ranged_cooldown",
)
_STAT_ADDITION_FIELDS = _STAT_MULTIPLIER_FIELDS


def normalize_enemy_key(value: object, default: str = "") -> str:
    return str(value or default).strip().lower().replace("-", "_").replace(" ", "_")


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _normalize_color(value: object, label: str) -> tuple[int, int, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{label} must be an RGB triplet")
    color = tuple(int(channel) for channel in value)
    if any(channel < 0 or channel > 255 for channel in color):
        raise ValueError(f"{label} must contain RGB values between 0 and 255")
    return color


def validate_enemy_variant_profile(variant: Mapping[str, Any], label: str) -> None:
    """Validate the optional procedural modifiers attached to one enemy variant."""

    for field_name in ("stat_multipliers", "stat_additions", "stat_overrides"):
        mapping = variant.get(field_name)
        if mapping is None:
            continue
        mapping = _require_mapping(mapping, f"{label}.{field_name}")
        for key, raw_value in mapping.items():
            stat_key = normalize_enemy_key(key)
            if stat_key not in _STAT_MULTIPLIER_FIELDS:
                raise ValueError(f"{label}.{field_name} uses unsupported stat {key!r}")
            try:
                float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label}.{field_name}[{stat_key!r}] must be numeric") from exc

    render_tint = variant.get("render_tint")
    if render_tint is not None:
        _normalize_color(render_tint, f"{label}.render_tint")


def apply_enemy_variant_profile(
    base_stats: Mapping[str, Any],
    variant: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Clone one enemy stat block and apply the variant's authored modifiers."""

    stats = dict(base_stats)
    if not variant:
        return stats

    multipliers = variant.get("stat_multipliers", {})
    additions = variant.get("stat_additions", {})
    overrides = variant.get("stat_overrides", {})

    if isinstance(multipliers, Mapping):
        for key, raw_value in multipliers.items():
            stat_key = normalize_enemy_key(key)
            if stat_key not in stats:
                continue
            stats[stat_key] = float(stats[stat_key]) * float(raw_value)

    if isinstance(additions, Mapping):
        for key, raw_value in additions.items():
            stat_key = normalize_enemy_key(key)
            if stat_key not in stats:
                continue
            stats[stat_key] = float(stats[stat_key]) + float(raw_value)

    if isinstance(overrides, Mapping):
        for key, raw_value in overrides.items():
            stat_key = normalize_enemy_key(key)
            if stat_key not in stats:
                continue
            stats[stat_key] = float(raw_value)

    render_tint = variant.get("render_tint")
    if render_tint is not None:
        stats["render_tint"] = _normalize_color(render_tint, "enemy variant render_tint")

    if "token_cost" in stats:
        stats["token_cost"] = max(1, int(round(float(stats["token_cost"]))))

    return stats
