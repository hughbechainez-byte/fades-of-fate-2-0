"""Deterministic level-complete statistics and celebration sequencing.

This module deliberately has no Pygame or game-object imports.  The gameplay
layer can feed fixed-step time and damage events into ``LevelStatTracker``, then
drive Dave/Shelly/Chief presentation from ``LevelCompleteTimeline``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import math
from typing import Any, Protocol


class PlayerPerformance(Protocol):
    score: int
    ko_count: int
    hit_count: int


def _non_negative_finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


@dataclass(frozen=True, slots=True)
class RankRules:
    """Data-driven weights and descending thresholds for a stage rank."""

    hit_value: float = 8.0
    ko_value: float = 125.0
    damage_penalty: float = 5.0
    par_seconds: float = 300.0
    early_second_bonus: float = 3.0
    overtime_second_penalty: float = 2.0
    thresholds: tuple[tuple[str, float], ...] = (
        ("S", 6500.0),
        ("A", 4500.0),
        ("B", 3000.0),
        ("C", 1500.0),
        ("D", 0.0),
    )

    def __post_init__(self) -> None:
        for name in (
            "hit_value",
            "ko_value",
            "damage_penalty",
            "par_seconds",
            "early_second_bonus",
            "overtime_second_penalty",
        ):
            _non_negative_finite(getattr(self, name), name)
        if not self.thresholds:
            raise ValueError("rank thresholds cannot be empty")
        previous = math.inf
        seen: set[str] = set()
        for rank, threshold in self.thresholds:
            if not str(rank).strip() or rank in seen:
                raise ValueError("rank names must be non-empty and unique")
            value = _non_negative_finite(threshold, f"threshold {rank}")
            if value > previous:
                raise ValueError("rank thresholds must be ordered highest to lowest")
            previous = value
            seen.add(rank)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> RankRules:
        allowed = set(cls.__dataclass_fields__)
        data = {key: value for key, value in values.items() if key in allowed}
        if "thresholds" in data:
            raw = data["thresholds"]
            if isinstance(raw, Mapping):
                data["thresholds"] = tuple((str(rank), float(score)) for rank, score in raw.items())
            else:
                data["thresholds"] = tuple((str(item[0]), float(item[1])) for item in raw)
        return cls(**data)

    def rating_points(
        self,
        *,
        completion_seconds: float,
        combined_score: int,
        kos: int,
        hits_landed: int,
        damage_taken: float,
    ) -> int:
        completion_seconds = _non_negative_finite(completion_seconds, "completion_seconds")
        damage_taken = _non_negative_finite(damage_taken, "damage_taken")
        early = max(0.0, self.par_seconds - completion_seconds)
        overtime = max(0.0, completion_seconds - self.par_seconds)
        raw = (
            max(0, int(combined_score))
            + max(0, int(kos)) * self.ko_value
            + max(0, int(hits_landed)) * self.hit_value
            - damage_taken * self.damage_penalty
            + early * self.early_second_bonus
            - overtime * self.overtime_second_penalty
        )
        return max(0, int(round(raw)))

    def rank_for_points(self, points: int) -> str:
        points = max(0, int(points))
        for rank, threshold in self.thresholds:
            if points >= threshold:
                return rank
        return self.thresholds[-1][0]


@dataclass(frozen=True, slots=True)
class CompletionStats:
    completion_seconds: float
    combined_score: int
    kos: int
    hits_landed: int
    damage_taken: float
    rating_points: int
    rank: str

    @property
    def formatted_time(self) -> str:
        total_seconds = max(0, int(round(self.completion_seconds)))
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def as_dict(self) -> dict[str, int | float | str]:
        return {
            "completion_seconds": self.completion_seconds,
            "completion_time": self.formatted_time,
            "combined_score": self.combined_score,
            "kos": self.kos,
            "hits_landed": self.hits_landed,
            "damage_taken": self.damage_taken,
            "rating_points": self.rating_points,
            "rank": self.rank,
        }


@dataclass(slots=True)
class LevelStatTracker:
    rules: RankRules = field(default_factory=RankRules)
    _elapsed_seconds: float = 0.0
    _damage_taken: float = 0.0
    _finished: CompletionStats | None = None

    @property
    def elapsed_seconds(self) -> float:
        return self._elapsed_seconds

    @property
    def finished(self) -> bool:
        return self._finished is not None

    def advance(self, dt: float) -> None:
        if self.finished:
            return
        self._elapsed_seconds += _non_negative_finite(dt, "dt")

    def record_damage(self, amount: float) -> None:
        if self.finished:
            raise RuntimeError("cannot record damage after level statistics are finished")
        self._damage_taken += _non_negative_finite(amount, "damage amount")

    def preview(self, players: Iterable[PlayerPerformance]) -> CompletionStats:
        return self._build_snapshot(players)

    def finish(self, players: Iterable[PlayerPerformance]) -> CompletionStats:
        if self._finished is None:
            self._finished = self._build_snapshot(players)
        return self._finished

    def _build_snapshot(self, players: Iterable[PlayerPerformance]) -> CompletionStats:
        roster = tuple(players)
        score = sum(max(0, int(player.score)) for player in roster)
        kos = sum(max(0, int(player.ko_count)) for player in roster)
        hits = sum(max(0, int(player.hit_count)) for player in roster)
        elapsed = round(self._elapsed_seconds, 3)
        damage = round(self._damage_taken, 1)
        points = self.rules.rating_points(
            completion_seconds=elapsed,
            combined_score=score,
            kos=kos,
            hits_landed=hits,
            damage_taken=damage,
        )
        return CompletionStats(
            completion_seconds=elapsed,
            combined_score=score,
            kos=kos,
            hits_landed=hits,
            damage_taken=damage,
            rating_points=points,
            rank=self.rules.rank_for_points(points),
        )

    def reset(self) -> None:
        self._elapsed_seconds = 0.0
        self._damage_taken = 0.0
        self._finished = None


@dataclass(frozen=True, slots=True)
class CelebrationFrame:
    phase: str
    elapsed_seconds: float
    phase_elapsed: float
    phase_progress: float
    show_results: bool
    events: tuple[str, ...] = ()


@dataclass(slots=True)
class LevelCompleteTimeline:
    """Fixed-time hug, treat toss, and persistent results sequence."""

    hug_seconds: float = 1.25
    treat_toss_seconds: float = 1.15
    treat_release_seconds: float = 0.38
    elapsed_seconds: float = 0.0
    _emitted: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.hug_seconds = _non_negative_finite(self.hug_seconds, "hug_seconds")
        self.treat_toss_seconds = _non_negative_finite(self.treat_toss_seconds, "treat_toss_seconds")
        self.treat_release_seconds = _non_negative_finite(self.treat_release_seconds, "treat_release_seconds")
        if self.hug_seconds <= 0.0 or self.treat_toss_seconds <= 0.0:
            raise ValueError("hug and treat-toss durations must be greater than zero")
        if self.treat_release_seconds > self.treat_toss_seconds:
            raise ValueError("treat release must occur during the treat-toss phase")

    @property
    def phase(self) -> str:
        if self.elapsed_seconds < self.hug_seconds:
            return "hug"
        if self.elapsed_seconds < self.hug_seconds + self.treat_toss_seconds:
            return "treat_toss"
        return "results"

    def current_frame(self, events: tuple[str, ...] = ()) -> CelebrationFrame:
        phase = self.phase
        if phase == "hug":
            phase_elapsed = self.elapsed_seconds
            duration = self.hug_seconds
        elif phase == "treat_toss":
            phase_elapsed = self.elapsed_seconds - self.hug_seconds
            duration = self.treat_toss_seconds
        else:
            phase_elapsed = self.elapsed_seconds - self.hug_seconds - self.treat_toss_seconds
            duration = 0.0
        progress = 1.0 if duration <= 0.0 else min(1.0, max(0.0, phase_elapsed / duration))
        return CelebrationFrame(
            phase=phase,
            elapsed_seconds=self.elapsed_seconds,
            phase_elapsed=max(0.0, phase_elapsed),
            phase_progress=progress,
            show_results=phase == "results",
            events=events,
        )

    def advance(self, dt: float) -> CelebrationFrame:
        previous = self.elapsed_seconds
        self.elapsed_seconds += _non_negative_finite(dt, "dt")
        milestones = (
            ("hug_complete", self.hug_seconds),
            ("treat_toss", self.hug_seconds),
            ("treat_release", self.hug_seconds + self.treat_release_seconds),
            ("results", self.hug_seconds + self.treat_toss_seconds),
        )
        events: list[str] = []
        for name, at_seconds in milestones:
            if name not in self._emitted and previous < at_seconds <= self.elapsed_seconds:
                self._emitted.add(name)
                events.append(name)
        return self.current_frame(tuple(events))

    def reset(self) -> None:
        self.elapsed_seconds = 0.0
        self._emitted.clear()
