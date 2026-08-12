"""Versioned save, options, progression, and replay-stat primitives.

The module intentionally has no Pygame or live-game imports.  Runtime code can
load it before constructing the renderer, apply the normalized option scalars,
then atomically persist a new immutable snapshot after a run.  Reads accept
plain UTF-8 and Windows-authored UTF-8 with a BOM; writes use canonical UTF-8.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any

from .atmosphere import AtmosphereState


SAVE_SCHEMA_VERSION = 2
SUPPORTED_SAVE_VERSIONS = (1, SAVE_SCHEMA_VERSION)
DEFAULT_FIRST_LEVEL_ID = "chapter_1_level_1"
DIFFICULTIES = ("story", "normal", "hard")
KNOWN_SUPER_ATTACK_CHARACTERS = ("black_dave", "shelly", "jermaine", "white_dave")
QUALITY_PRESET_NAMES = ("performance", "balanced", "cinematic", "accessible")
LOAD_STATUSES = ("loaded", "missing", "invalid", "unsupported_version")

_QUALITY_PRESET_VALUES: dict[str, dict[str, Any]] = {
    "performance": {
        "hud_scale": 1.0,
        "hud_opacity": 0.90,
        "shake_intensity": 0.65,
        "flash_intensity": 0.65,
        "particle_density": 0.55,
        "high_contrast": False,
        "pickup_outline": True,
        "dialogue_speed": 1.0,
    },
    "balanced": {
        "hud_scale": 1.0,
        "hud_opacity": 0.94,
        "shake_intensity": 1.0,
        "flash_intensity": 0.85,
        "particle_density": 1.0,
        "high_contrast": False,
        "pickup_outline": True,
        "dialogue_speed": 1.0,
    },
    "cinematic": {
        "hud_scale": 1.0,
        "hud_opacity": 0.96,
        "shake_intensity": 1.20,
        "flash_intensity": 1.0,
        "particle_density": 1.45,
        "high_contrast": False,
        "pickup_outline": True,
        "dialogue_speed": 1.0,
    },
    "accessible": {
        "hud_scale": 1.20,
        "hud_opacity": 1.0,
        "shake_intensity": 0.20,
        "flash_intensity": 0.25,
        "particle_density": 0.70,
        "high_contrast": True,
        "pickup_outline": True,
        "dialogue_speed": 0.80,
    },
}


def _bounded_float(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a number") from error
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{label} must be between {minimum:g} and {maximum:g}")
    return result


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"{label} must be a non-negative integer")
        return value
    try:
        result = int(value)
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a non-negative integer") from error
    if not math.isfinite(numeric) or result < 0 or result != numeric:
        raise ValueError(f"{label} must be a non-negative integer")
    return result


def _non_negative_float(value: Any, label: str) -> float:
    return _bounded_float(value, label, 0.0, float("1e308"))


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be true or false")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _rank_label(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value.strip().upper()


def _unique_ids(values: Any, label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise ValueError(f"{label} must be an array")
    result: list[str] = []
    for index, value in enumerate(values):
        item = _identifier(value, f"{label}[{index}]")
        if item not in result:
            result.append(item)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class GameOptions:
    """Normalized graphics/accessibility values plus the gameplay difficulty.

    Intensity and density values are multipliers.  ``dialogue_speed`` is also a
    multiplier, so values below one deliberately leave text on screen longer.
    """

    quality_preset: str = "balanced"
    hud_scale: float = 1.0
    hud_opacity: float = 0.94
    shake_intensity: float = 1.0
    flash_intensity: float = 0.85
    particle_density: float = 1.0
    high_contrast: bool = False
    pickup_outline: bool = True
    dialogue_speed: float = 1.0
    difficulty: str = "normal"
    super_attack_characters: tuple[str, ...] = field(default_factory=lambda: KNOWN_SUPER_ATTACK_CHARACTERS)

    def __post_init__(self) -> None:
        preset = str(self.quality_preset).strip().lower()
        if preset not in (*QUALITY_PRESET_NAMES, "custom"):
            raise ValueError(f"unknown quality preset: {preset or '<empty>'}")
        difficulty = str(self.difficulty).strip().lower()
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"unknown difficulty: {difficulty or '<empty>'}")
        object.__setattr__(self, "quality_preset", preset)
        object.__setattr__(self, "difficulty", difficulty)
        super_characters = tuple(
            _identifier(name, "super_attack_characters")
            for name in self.super_attack_characters
        )
        super_set = []
        for name in super_characters:
            if name not in KNOWN_SUPER_ATTACK_CHARACTERS:
                raise ValueError(f"unknown character in super_attack_characters: {name}")
            if name not in super_set:
                super_set.append(name)
        object.__setattr__(self, "super_attack_characters", tuple(super_set))
        object.__setattr__(self, "hud_scale", _bounded_float(self.hud_scale, "hud_scale", 0.80, 1.50))
        object.__setattr__(self, "hud_opacity", _bounded_float(self.hud_opacity, "hud_opacity", 0.40, 1.0))
        object.__setattr__(
            self,
            "shake_intensity",
            _bounded_float(self.shake_intensity, "shake_intensity", 0.0, 1.50),
        )
        object.__setattr__(
            self,
            "flash_intensity",
            _bounded_float(self.flash_intensity, "flash_intensity", 0.0, 1.0),
        )
        object.__setattr__(
            self,
            "particle_density",
            _bounded_float(self.particle_density, "particle_density", 0.25, 2.0),
        )
        object.__setattr__(
            self,
            "dialogue_speed",
            _bounded_float(self.dialogue_speed, "dialogue_speed", 0.50, 2.0),
        )
        object.__setattr__(self, "high_contrast", _boolean(self.high_contrast, "high_contrast"))
        object.__setattr__(self, "pickup_outline", _boolean(self.pickup_outline, "pickup_outline"))

    @classmethod
    def from_preset(cls, preset: str, *, difficulty: str = "normal", **overrides: Any) -> GameOptions:
        key = str(preset).strip().lower()
        if key not in _QUALITY_PRESET_VALUES:
            raise ValueError(f"unknown quality preset: {key or '<empty>'}")
        allowed = set(cls.__dataclass_fields__) - {"quality_preset"}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(f"unknown option override: {sorted(unknown)[0]}")
        values = dict(_QUALITY_PRESET_VALUES[key])
        values.update(overrides)
        return cls(quality_preset=key, difficulty=difficulty, **values)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> GameOptions:
        if not isinstance(values, Mapping):
            raise ValueError("options must be an object")
        preset = str(values.get("quality_preset", "balanced")).strip().lower()
        base = cls.from_preset(preset if preset in _QUALITY_PRESET_VALUES else "balanced")
        allowed = set(cls.__dataclass_fields__)
        payload = {name: values[name] for name in allowed if name in values}
        return replace(base, **payload)

    def apply_preset(self, preset: str) -> GameOptions:
        """Reset presentation values while preserving the chosen difficulty."""

        return self.from_preset(preset, difficulty=self.difficulty)

    def with_overrides(self, **changes: Any) -> GameOptions:
        allowed = set(self.__dataclass_fields__)
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unknown option override: {sorted(unknown)[0]}")
        if any(name != "difficulty" for name in changes) and "quality_preset" not in changes:
            changes["quality_preset"] = "custom"
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


QUALITY_PRESETS: Mapping[str, GameOptions] = MappingProxyType(
    {name: GameOptions.from_preset(name) for name in QUALITY_PRESET_NAMES}
)


@dataclass(frozen=True, slots=True)
class RunStats:
    """One deterministic level attempt, successful or otherwise."""

    completed: bool
    score: int = 0
    completion_seconds: float | None = None
    kos: int = 0
    hits_landed: int = 0
    damage_taken: float = 0.0
    rank: str = ""
    difficulty: str = "normal"

    def __post_init__(self) -> None:
        object.__setattr__(self, "completed", _boolean(self.completed, "completed"))
        object.__setattr__(self, "score", _non_negative_int(self.score, "score"))
        object.__setattr__(self, "kos", _non_negative_int(self.kos, "kos"))
        object.__setattr__(self, "hits_landed", _non_negative_int(self.hits_landed, "hits_landed"))
        object.__setattr__(self, "damage_taken", _non_negative_float(self.damage_taken, "damage_taken"))
        if self.completion_seconds is not None:
            object.__setattr__(
                self,
                "completion_seconds",
                _non_negative_float(self.completion_seconds, "completion_seconds"),
            )
        rank = _rank_label(self.rank, "rank")
        difficulty = str(self.difficulty).strip().lower()
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"unknown difficulty: {difficulty or '<empty>'}")
        if self.completed and self.completion_seconds is None:
            raise ValueError("a completed run requires completion_seconds")
        if self.completed and not rank:
            raise ValueError("a completed run requires a rank")
        object.__setattr__(self, "rank", rank)
        object.__setattr__(self, "difficulty", difficulty)

    @classmethod
    def from_completion(
        cls,
        completion: Mapping[str, Any] | object,
        *,
        difficulty: str = "normal",
        completed: bool = True,
    ) -> RunStats:
        def read(name: str, default: Any = 0) -> Any:
            if isinstance(completion, Mapping):
                return completion.get(name, default)
            return getattr(completion, name, default)

        return cls(
            completed=completed,
            score=read("combined_score", read("score", 0)),
            completion_seconds=read("completion_seconds", None),
            kos=read("kos", 0),
            hits_landed=read("hits_landed", 0),
            damage_taken=read("damage_taken", 0.0),
            rank=read("rank", ""),
            difficulty=difficulty,
        )


_RANK_PRIORITY = {rank: index for index, rank in enumerate(("S", "A", "B", "C", "D"))}


@dataclass(frozen=True, slots=True)
class ReplayStats:
    plays: int = 0
    clears: int = 0
    best_score: int = 0
    best_completion_seconds: float | None = None
    best_rank: str = ""
    total_kos: int = 0
    total_hits_landed: int = 0
    total_damage_taken: float = 0.0
    last_score: int = 0
    last_completion_seconds: float | None = None
    last_rank: str = ""
    last_difficulty: str = "normal"

    def __post_init__(self) -> None:
        for name in ("plays", "clears", "best_score", "total_kos", "total_hits_landed", "last_score"):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        if self.clears > self.plays:
            raise ValueError("replay clears cannot exceed plays")
        for name in ("best_completion_seconds", "last_completion_seconds"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _non_negative_float(value, name))
        object.__setattr__(
            self,
            "total_damage_taken",
            _non_negative_float(self.total_damage_taken, "total_damage_taken"),
        )
        difficulty = str(self.last_difficulty).strip().lower()
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"unknown difficulty: {difficulty or '<empty>'}")
        object.__setattr__(self, "last_difficulty", difficulty)
        object.__setattr__(self, "best_rank", _rank_label(self.best_rank, "best_rank"))
        object.__setattr__(self, "last_rank", _rank_label(self.last_rank, "last_rank"))

    def record(self, run: RunStats) -> ReplayStats:
        if not isinstance(run, RunStats):
            raise TypeError("run must be RunStats")
        best_time = self.best_completion_seconds
        if run.completed and run.completion_seconds is not None:
            best_time = run.completion_seconds if best_time is None else min(best_time, run.completion_seconds)
        best_rank = self.best_rank
        if run.completed and run.rank:
            current_priority = _RANK_PRIORITY.get(best_rank, len(_RANK_PRIORITY))
            run_priority = _RANK_PRIORITY.get(run.rank, len(_RANK_PRIORITY))
            if not best_rank or run_priority < current_priority:
                best_rank = run.rank
        return ReplayStats(
            plays=self.plays + 1,
            clears=self.clears + int(run.completed),
            best_score=max(self.best_score, run.score),
            best_completion_seconds=best_time,
            best_rank=best_rank,
            total_kos=self.total_kos + run.kos,
            total_hits_landed=self.total_hits_landed + run.hits_landed,
            total_damage_taken=round(self.total_damage_taken + run.damage_taken, 3),
            last_score=run.score,
            last_completion_seconds=run.completion_seconds,
            last_rank=run.rank,
            last_difficulty=run.difficulty,
        )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> ReplayStats:
        if not isinstance(values, Mapping):
            raise ValueError("replay stats must be an object")
        allowed = set(cls.__dataclass_fields__)
        return cls(**{name: values[name] for name in allowed if name in values})

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ProgressionState:
    unlocked_level_ids: tuple[str, ...] = (DEFAULT_FIRST_LEVEL_ID,)
    completed_level_ids: tuple[str, ...] = ()
    last_level_id: str | None = None
    replay_stats: Mapping[str, ReplayStats] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unlocked = _unique_ids(self.unlocked_level_ids, "unlocked_level_ids")
        completed = _unique_ids(self.completed_level_ids, "completed_level_ids")
        if not unlocked:
            unlocked = (DEFAULT_FIRST_LEVEL_ID,)
        unlocked_list = list(unlocked)
        for level_id in completed:
            if level_id not in unlocked_list:
                unlocked_list.append(level_id)
        last_level = None if self.last_level_id is None else _identifier(self.last_level_id, "last_level_id")
        if not isinstance(self.replay_stats, Mapping):
            raise ValueError("replay_stats must be an object")
        stats: dict[str, ReplayStats] = {}
        for raw_level_id, raw_stats in self.replay_stats.items():
            level_id = _identifier(raw_level_id, "replay_stats level id")
            stats[level_id] = raw_stats if isinstance(raw_stats, ReplayStats) else ReplayStats.from_mapping(raw_stats)
        object.__setattr__(self, "unlocked_level_ids", tuple(unlocked_list))
        object.__setattr__(self, "completed_level_ids", completed)
        object.__setattr__(self, "last_level_id", last_level)
        object.__setattr__(self, "replay_stats", MappingProxyType(dict(sorted(stats.items()))))

    @classmethod
    def new(cls, first_level_id: str = DEFAULT_FIRST_LEVEL_ID) -> ProgressionState:
        return cls(unlocked_level_ids=(_identifier(first_level_id, "first_level_id"),))

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> ProgressionState:
        if not isinstance(values, Mapping):
            raise ValueError("progression must be an object")
        replay_values = values.get("replay_stats", {})
        if not isinstance(replay_values, Mapping):
            raise ValueError("progression.replay_stats must be an object")
        return cls(
            unlocked_level_ids=_unique_ids(
                values.get("unlocked_level_ids", [DEFAULT_FIRST_LEVEL_ID]),
                "unlocked_level_ids",
            ),
            completed_level_ids=_unique_ids(values.get("completed_level_ids", []), "completed_level_ids"),
            last_level_id=values.get("last_level_id"),
            replay_stats={
                str(level_id): ReplayStats.from_mapping(stats)
                for level_id, stats in replay_values.items()
            },
        )

    def is_unlocked(self, level_id: str) -> bool:
        return str(level_id).strip() in self.unlocked_level_ids

    def stats_for(self, level_id: str) -> ReplayStats:
        return self.replay_stats.get(str(level_id).strip(), ReplayStats())

    def record_run(
        self,
        level_id: str,
        run: RunStats,
        *,
        next_level_id: str | None = None,
    ) -> ProgressionState:
        if not isinstance(run, RunStats):
            raise TypeError("run must be RunStats")
        current_id = _identifier(level_id, "level_id")
        next_id = None if next_level_id is None else _identifier(next_level_id, "next_level_id")
        unlocked = list(self.unlocked_level_ids)
        completed = list(self.completed_level_ids)
        if current_id not in unlocked:
            unlocked.append(current_id)
        if run.completed and current_id not in completed:
            completed.append(current_id)
        if run.completed and next_id is not None and next_id not in unlocked:
            unlocked.append(next_id)
        stats = dict(self.replay_stats)
        stats[current_id] = stats.get(current_id, ReplayStats()).record(run)
        return ProgressionState(
            unlocked_level_ids=tuple(unlocked),
            completed_level_ids=tuple(completed),
            last_level_id=current_id,
            replay_stats=stats,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "unlocked_level_ids": list(self.unlocked_level_ids),
            "completed_level_ids": list(self.completed_level_ids),
            "last_level_id": self.last_level_id,
            "replay_stats": {
                level_id: stats.to_dict()
                for level_id, stats in sorted(self.replay_stats.items())
            },
        }


@dataclass(frozen=True, slots=True)
class SaveData:
    options: GameOptions = field(default_factory=GameOptions)
    progression: ProgressionState = field(default_factory=ProgressionState)
    atmosphere: AtmosphereState = field(default_factory=AtmosphereState.new)
    schema_version: int = SAVE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        version = _non_negative_int(self.schema_version, "schema_version")
        if version not in SUPPORTED_SAVE_VERSIONS:
            raise ValueError(f"unsupported save schema version: {version}")
        if not isinstance(self.options, GameOptions):
            raise ValueError("options must be GameOptions")
        if not isinstance(self.progression, ProgressionState):
            raise ValueError("progression must be ProgressionState")
        if not isinstance(self.atmosphere, AtmosphereState):
            raise ValueError("atmosphere must be AtmosphereState")
        object.__setattr__(self, "schema_version", SAVE_SCHEMA_VERSION)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> SaveData:
        if not isinstance(values, Mapping):
            raise ValueError("save root must be an object")
        version = _non_negative_int(
            values.get("schema_version", SAVE_SCHEMA_VERSION),
            "schema_version",
        )
        if version not in SUPPORTED_SAVE_VERSIONS:
            raise ValueError(f"unsupported save schema version: {version}")
        return cls(
            options=GameOptions.from_mapping(values.get("options", {})),
            progression=ProgressionState.from_mapping(values.get("progression", {})),
            atmosphere=AtmosphereState.from_mapping(
                values.get("atmosphere", {})
                if version == SAVE_SCHEMA_VERSION
                else {}
            ),
            schema_version=version,
        )

    def record_run(
        self,
        level_id: str,
        run: RunStats,
        *,
        next_level_id: str | None = None,
    ) -> SaveData:
        return replace(
            self,
            progression=self.progression.record_run(level_id, run, next_level_id=next_level_id),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "options": self.options.to_dict(),
            "progression": self.progression.to_dict(),
            "atmosphere": self.atmosphere.to_mapping(),
        }


@dataclass(frozen=True, slots=True)
class LoadResult:
    data: SaveData
    status: str
    message: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.data, SaveData):
            raise ValueError("load result data must be SaveData")
        if self.status not in LOAD_STATUSES:
            raise ValueError(f"unknown load status: {self.status}")

    @property
    def loaded(self) -> bool:
        return self.status == "loaded"

    @property
    def recovered(self) -> bool:
        return self.status in {"invalid", "unsupported_version"}


def load_save(path: str | os.PathLike[str], *, default: SaveData | None = None) -> LoadResult:
    """Read one save without modifying or deleting missing/corrupt input."""

    save_path = Path(path)
    if default is not None and not isinstance(default, SaveData):
        raise TypeError("default must be SaveData")
    fallback = default or SaveData()
    try:
        text = save_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return LoadResult(fallback, "missing", "save file does not exist")
    except (OSError, UnicodeError) as error:
        return LoadResult(fallback, "invalid", f"save file could not be read: {error}")
    try:
        raw = json.loads(text)
        if not isinstance(raw, Mapping):
            raise ValueError("save root must be an object")
        version = _non_negative_int(
            raw.get("schema_version", SAVE_SCHEMA_VERSION),
            "schema_version",
        )
        if version not in SUPPORTED_SAVE_VERSIONS:
            return LoadResult(
                fallback,
                "unsupported_version",
                f"save schema {version} is not supported by schema {SAVE_SCHEMA_VERSION}",
            )
        return LoadResult(SaveData.from_mapping(raw), "loaded")
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return LoadResult(fallback, "invalid", f"save data is invalid: {error}")


def save_data(path: str | os.PathLike[str], data: SaveData) -> None:
    """Atomically replace ``path`` with deterministic, BOM-free UTF-8 JSON."""

    if not isinstance(data, SaveData):
        raise TypeError("data must be SaveData")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        data.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class SaveRepository:
    path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))

    def load(self, *, default: SaveData | None = None) -> LoadResult:
        return load_save(self.path, default=default)

    def save(self, data: SaveData) -> None:
        save_data(self.path, data)


__all__ = [
    "DEFAULT_FIRST_LEVEL_ID",
    "DIFFICULTIES",
    "GameOptions",
    "LOAD_STATUSES",
    "LoadResult",
    "ProgressionState",
    "QUALITY_PRESETS",
    "QUALITY_PRESET_NAMES",
    "ReplayStats",
    "RunStats",
    "SAVE_SCHEMA_VERSION",
    "SaveData",
    "SaveRepository",
    "load_save",
    "save_data",
]
