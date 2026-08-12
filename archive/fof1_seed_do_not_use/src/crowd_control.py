"""Pure mechanical crowd displacement used by route execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CrowdTarget:
    entity_id: str
    normal_enemy: bool
    boss: bool = False
    armor: float = 0.0
    push_resistance: float = 0.0


@dataclass(frozen=True, slots=True)
class CrowdPush:
    entity_id: str
    distance: float


def apply_crowd_push(targets: Iterable[CrowdTarget], *, distance: float, cap: int, armor_limit: float = 0.0) -> tuple[CrowdPush, ...]:
    """Return capped displacement only for eligible ordinary enemies.

    This intentionally neither mutates targets nor carries VFX/damage data.
    """
    if distance <= 0.0:
        raise ValueError("distance must be positive")
    if cap < 1:
        raise ValueError("cap must be positive")
    result: list[CrowdPush] = []
    for target in targets:
        if len(result) == cap:
            break
        if not target.normal_enemy or target.boss or target.armor > armor_limit:
            continue
        applied = distance * max(0.0, 1.0 - min(1.0, target.push_resistance))
        if applied > 0.0:
            result.append(CrowdPush(target.entity_id, applied))
    return tuple(result)
