"""Deterministic in-stage loading handoffs for authored encounter transitions."""

from __future__ import annotations

from dataclasses import dataclass
import math


def _seconds(value: float, label: str, *, positive: bool = False) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or (positive and result <= 0.0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{label} must be finite and {qualifier}")
    return result


@dataclass(frozen=True, slots=True)
class TransitionFrame:
    elapsed_seconds: float
    progress: float
    overlay_alpha: float
    events: tuple[str, ...]
    finished: bool


@dataclass(slots=True)
class BossLoadingTransition:
    """Fade in, relocate at blackout, then fade into the Couch encounter."""

    duration_seconds: float = 2.4
    relocate_seconds: float = 1.05
    elapsed_seconds: float = 0.0
    _relocated: bool = False
    _finished: bool = False

    def __post_init__(self) -> None:
        self.duration_seconds = _seconds(self.duration_seconds, "duration_seconds", positive=True)
        self.relocate_seconds = _seconds(self.relocate_seconds, "relocate_seconds")
        if not 0.0 < self.relocate_seconds < self.duration_seconds:
            raise ValueError("relocate_seconds must occur inside the transition")

    @property
    def finished(self) -> bool:
        return self._finished

    def current_frame(self, events: tuple[str, ...] = ()) -> TransitionFrame:
        progress = min(1.0, max(0.0, self.elapsed_seconds / self.duration_seconds))
        if self.elapsed_seconds <= self.relocate_seconds:
            alpha = self.elapsed_seconds / self.relocate_seconds
        else:
            fade_out = self.duration_seconds - self.relocate_seconds
            alpha = (self.duration_seconds - self.elapsed_seconds) / fade_out
        return TransitionFrame(
            elapsed_seconds=self.elapsed_seconds,
            progress=progress,
            overlay_alpha=min(1.0, max(0.0, alpha)),
            events=events,
            finished=self._finished,
        )

    def advance(self, dt: float) -> TransitionFrame:
        dt = _seconds(dt, "dt")
        previous = self.elapsed_seconds
        self.elapsed_seconds = min(self.duration_seconds, self.elapsed_seconds + dt)
        events: list[str] = []
        if not self._relocated and previous < self.relocate_seconds <= self.elapsed_seconds:
            self._relocated = True
            events.append("relocate")
        if not self._finished and previous < self.duration_seconds <= self.elapsed_seconds:
            self._finished = True
            events.append("finished")
        return self.current_frame(tuple(events))

    def reset(self) -> None:
        self.elapsed_seconds = 0.0
        self._relocated = False
        self._finished = False


__all__ = ["BossLoadingTransition", "TransitionFrame"]
