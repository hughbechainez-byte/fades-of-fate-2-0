"""Deterministic authored outro timelines for campaign levels.

The module owns presentation timing and explicit narrative state only.
Rendering, audio, and campaign progression consume :class:`LevelOutroFrame`
without introducing frame-rate dependent scene logic.  Jerry's spoken beats
never advance on a timer: a fresh player input is required for each one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math


def _positive_seconds(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return result


def _non_negative_seconds(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


@dataclass(frozen=True, slots=True)
class OutroBeat:
    """Authored presentation data for one renderer-independent scene beat."""

    name: str
    speaker: str | None
    dialogue: str
    camera_focus: str
    jerry_pose: str
    party_pose: str


JERRY_LEVEL_ONE_BEATS: tuple[OutroBeat, ...] = (
    OutroBeat(
        name="arrival",
        speaker=None,
        dialogue="",
        camera_focus="jerry_arrives_at_el_cilantro_curb",
        jerry_pose="walker_arrival_then_settle",
        party_pose="turn_toward_jerry",
    ),
    OutroBeat(
        name="warning",
        speaker="Jerry",
        dialogue="Hey... I think I just saw Couch over by the 7-Eleven.",
        camera_focus="jerry_hat_shadow_closeup",
        jerry_pose="walker_warning",
        party_pose="listen_to_jerry",
    ),
    OutroBeat(
        name="clarification",
        speaker="Jerry",
        dialogue=(
            "I passed her on my way here—to El Cilantro, the Mexican food "
            "restaurant next to Goodwill."
        ),
        camera_focus="jerry_points_back_toward_seven_eleven",
        jerry_pose="walker_point_back",
        party_pose="follow_jerry_gesture",
    ),
    OutroBeat(
        name="reaction",
        speaker="Black Dave",
        dialogue="The 7-Eleven. Got it. Thanks, Jerry.",
        camera_focus="party_reaction",
        jerry_pose="walker_settled",
        party_pose="dave_acknowledges_shelly_and_chief_ready",
    ),
    OutroBeat(
        name="finished",
        speaker=None,
        dialogue="",
        camera_focus="route_to_seven_eleven",
        jerry_pose="walker_idle",
        party_pose="ready_to_depart",
    ),
)

WHEELCHAIR_CHRIS_LEVEL_TWO_BEATS: tuple[OutroBeat, ...] = (
    OutroBeat(
        name="arrival",
        speaker=None,
        dialogue="",
        camera_focus="wheelchair_chris_arrival",
        jerry_pose="walker_arrival_then_settle",
        party_pose="turn_toward_jerry",
    ),
    OutroBeat(
        name="warning",
        speaker="Wheelchair Chris",
        dialogue="I heard DeBo got out of jail.",
        camera_focus="wheelchair_chris_warning",
        jerry_pose="walker_warning",
        party_pose="listen_to_jerry",
    ),
    OutroBeat(
        name="clarification",
        speaker="Wheelchair Chris",
        dialogue="He's at the promenade.",
        camera_focus="wheelchair_chris_point",
        jerry_pose="walker_point_back",
        party_pose="follow_jerry_gesture",
    ),
    OutroBeat(
        name="finished",
        speaker="Wheelchair Chris",
        dialogue="Chris points the party south.",
        camera_focus="promenade_route_ahead",
        jerry_pose="walker_idle",
        party_pose="ready_to_depart",
    ),
)


@dataclass(frozen=True, slots=True)
class LevelOutroFrame:
    """Complete presentation snapshot returned after every simulation step."""

    beat: str
    elapsed_seconds: float
    beat_elapsed: float
    beat_progress: float
    speaker: str | None
    dialogue: str
    camera_focus: str
    jerry_pose: str
    party_pose: str
    events: tuple[str, ...]
    finished: bool
    awaiting_continue: bool


@dataclass(slots=True)
class JerryLevelOneOutro:
    """Five-beat Level 1 Jerry scene with deterministic input debouncing.

    Jerry gets a short arrival animation, then *every displayed beat* waits
    indefinitely for a fresh advance edge. ``advance_input`` and
    ``skip_input`` deliberately accept raw held-button state: only a rising
    edge acts, so a held key/button cannot race through the conversation.
    Skip remains an explicit opt-in action and suppresses unplayed dialogue
    milestones.

    The three legacy dialogue-duration fields remain part of the public
    constructor for compatibility with saved test fixtures and tooling. They
    now describe the nominal scene length only; they never progress dialogue.
    """

    arrival_seconds: float = 1.20
    warning_seconds: float = 3.20
    clarification_seconds: float = 4.25
    reaction_seconds: float = 2.10
    elapsed_seconds: float = 0.0
    _emitted: set[str] = field(default_factory=set)
    _advance_was_down: bool = False
    _skip_was_down: bool = False
    _beat_index: int = field(default=0, init=False)
    _beat_elapsed: float = field(default=0.0, init=False)
    _arrival_ready: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.arrival_seconds = _positive_seconds(self.arrival_seconds, "arrival_seconds")
        self.warning_seconds = _positive_seconds(self.warning_seconds, "warning_seconds")
        self.clarification_seconds = _positive_seconds(
            self.clarification_seconds, "clarification_seconds"
        )
        self.reaction_seconds = _positive_seconds(self.reaction_seconds, "reaction_seconds")
        self.elapsed_seconds = _non_negative_seconds(self.elapsed_seconds, "elapsed_seconds")
        # Supplying elapsed time is useful for renderer tooling.  It may settle
        # the arrival animation, but it never silently skips a dialogue beat.
        self._beat_elapsed = self.elapsed_seconds
        self._arrival_ready = self._beat_elapsed >= self.arrival_seconds

    @property
    def boundaries(self) -> tuple[float, float, float, float]:
        arrival = self.arrival_seconds
        warning = arrival + self.warning_seconds
        clarification = warning + self.clarification_seconds
        finished = clarification + self.reaction_seconds
        return arrival, warning, clarification, finished

    @property
    def total_seconds(self) -> float:
        """Return the authored nominal duration, not an auto-finish deadline."""

        return sum(
            (
                self.arrival_seconds,
                self.warning_seconds,
                self.clarification_seconds,
                self.reaction_seconds,
            )
        )

    @property
    def finished(self) -> bool:
        return self._beat_index >= len(JERRY_LEVEL_ONE_BEATS) - 1

    @property
    def beat_index(self) -> int:
        return min(self._beat_index, len(JERRY_LEVEL_ONE_BEATS) - 1)

    @property
    def beat(self) -> str:
        return JERRY_LEVEL_ONE_BEATS[self.beat_index].name

    def current_frame(self, events: tuple[str, ...] = ()) -> LevelOutroFrame:
        index = self.beat_index
        authored = JERRY_LEVEL_ONE_BEATS[index]
        if authored.name == "finished":
            beat_elapsed = 0.0
            progress = 1.0
        elif authored.name == "arrival":
            beat_elapsed = self._beat_elapsed
            progress = min(1.0, max(0.0, beat_elapsed / self.arrival_seconds))
        else:
            # The dialogue has no countdown.  A full value keeps renderer
            # contracts simple while making it clear this is not a timer.
            beat_elapsed = self._beat_elapsed
            progress = 1.0
        return LevelOutroFrame(
            beat=authored.name,
            elapsed_seconds=self.elapsed_seconds,
            beat_elapsed=beat_elapsed,
            beat_progress=progress,
            speaker=authored.speaker,
            dialogue=authored.dialogue,
            camera_focus=authored.camera_focus,
            jerry_pose=authored.jerry_pose,
            party_pose=authored.party_pose,
            events=events,
            finished=self.finished,
            awaiting_continue=(
                not self.finished
                and (authored.name != "arrival" or self._arrival_ready)
            ),
        )

    def _emit_once(self, *names: str) -> tuple[str, ...]:
        events: list[str] = []
        for name in names:
            if name not in self._emitted:
                self._emitted.add(name)
                events.append(name)
        return tuple(events)

    def _advance_to_next_beat(self) -> tuple[str, ...]:
        """Move one explicit beat forward and report its narration milestone."""

        if self.finished:
            return ()
        self._beat_index = min(self._beat_index + 1, len(JERRY_LEVEL_ONE_BEATS) - 1)
        self._beat_elapsed = 0.0
        milestone_for_index = {
            1: ("warning_started",),
            2: ("clarification_started",),
            3: ("reaction_started",),
            4: ("finished",),
        }
        return self._emit_once(*milestone_for_index.get(self._beat_index, ()))

    def advance(
        self,
        dt: float,
        *,
        advance_input: bool = False,
        skip_input: bool = False,
    ) -> LevelOutroFrame:
        """Advance presentation time and react to explicit held-input edges."""

        dt = _non_negative_seconds(dt, "dt")
        advance_down = bool(advance_input)
        skip_down = bool(skip_input)
        advance_edge = advance_down and not self._advance_was_down
        skip_edge = skip_down and not self._skip_was_down
        self._advance_was_down = advance_down
        self._skip_was_down = skip_down

        if self.finished:
            return self.current_frame()

        if skip_edge:
            self.elapsed_seconds += dt
            self._beat_index = len(JERRY_LEVEL_ONE_BEATS) - 1
            self._beat_elapsed = 0.0
            self._arrival_ready = True
            self._emitted.update({"jerry_settled", "finished"})
            return self.current_frame(("skipped", "finished"))

        self.elapsed_seconds += dt
        if self.beat_index == 0:
            was_ready = self._arrival_ready
            self._beat_elapsed += dt
            self._arrival_ready = self._beat_elapsed >= self.arrival_seconds
            if self._arrival_ready and not was_ready:
                # Do not let a button held during the arrival consume the
                # first dialogue beat the instant it becomes visible.
                return self.current_frame(self._emit_once("jerry_settled"))
            if not self._arrival_ready:
                return self.current_frame()
            if advance_edge:
                return self.current_frame(self._advance_to_next_beat())
            return self.current_frame()

        self._beat_elapsed += dt
        if advance_edge:
            return self.current_frame(self._advance_to_next_beat())
        return self.current_frame()

    def reset(self) -> None:
        self.elapsed_seconds = 0.0
        self._emitted.clear()
        self._advance_was_down = False
        self._skip_was_down = False
        self._beat_index = 0
        self._beat_elapsed = 0.0
        self._arrival_ready = False


@dataclass(slots=True)
class WheelchairChrisLevelTwoOutro:
    arrival_seconds: float = 1.20
    warning_seconds: float = 3.20
    clarification_seconds: float = 3.40
    elapsed_seconds: float = 0.0
    _emitted: set[str] = field(default_factory=set)
    _advance_was_down: bool = False
    _skip_was_down: bool = False
    _beat_index: int = field(default=0, init=False)
    _beat_elapsed: float = field(default=0.0, init=False)
    _arrival_ready: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.arrival_seconds = _positive_seconds(self.arrival_seconds, "arrival_seconds")
        self.warning_seconds = _positive_seconds(self.warning_seconds, "warning_seconds")
        self.clarification_seconds = _positive_seconds(self.clarification_seconds, "clarification_seconds")
        self.elapsed_seconds = _non_negative_seconds(self.elapsed_seconds, "elapsed_seconds")
        self._beat_elapsed = self.elapsed_seconds
        self._arrival_ready = self._beat_elapsed >= self.arrival_seconds

    @property
    def finished(self) -> bool:
        return self._beat_index >= len(WHEELCHAIR_CHRIS_LEVEL_TWO_BEATS) - 1

    @property
    def beat_index(self) -> int:
        return min(self._beat_index, len(WHEELCHAIR_CHRIS_LEVEL_TWO_BEATS) - 1)

    @property
    def beat(self) -> str:
        return WHEELCHAIR_CHRIS_LEVEL_TWO_BEATS[self.beat_index].name

    def current_frame(self, events: tuple[str, ...] = ()) -> LevelOutroFrame:
        authored = WHEELCHAIR_CHRIS_LEVEL_TWO_BEATS[self.beat_index]
        if authored.name == "arrival":
            beat_elapsed = self._beat_elapsed
            progress = min(1.0, max(0.0, beat_elapsed / self.arrival_seconds))
        else:
            beat_elapsed = self._beat_elapsed
            progress = 1.0
        return LevelOutroFrame(
            beat=authored.name,
            elapsed_seconds=self.elapsed_seconds,
            beat_elapsed=beat_elapsed,
            beat_progress=progress,
            speaker=authored.speaker,
            dialogue=authored.dialogue,
            camera_focus=authored.camera_focus,
            jerry_pose=authored.jerry_pose,
            party_pose=authored.party_pose,
            events=events,
            finished=self.finished,
            awaiting_continue=(not self.finished and (authored.name != "arrival" or self._arrival_ready)),
        )

    def _emit_once(self, *names: str) -> tuple[str, ...]:
        events: list[str] = []
        for name in names:
            if name not in self._emitted:
                self._emitted.add(name)
                events.append(name)
        return tuple(events)

    def _advance_to_next_beat(self) -> tuple[str, ...]:
        if self.finished:
            return ()
        self._beat_index = min(self._beat_index + 1, len(WHEELCHAIR_CHRIS_LEVEL_TWO_BEATS) - 1)
        self._beat_elapsed = 0.0
        milestone_for_index = {
            1: ("warning_started",),
            2: ("clarification_started",),
            3: ("finished",),
        }
        return self._emit_once(*milestone_for_index.get(self._beat_index, ()))

    def advance(self, dt: float, *, advance_input: bool = False, skip_input: bool = False) -> LevelOutroFrame:
        dt = _non_negative_seconds(dt, "dt")
        advance_down = bool(advance_input)
        skip_down = bool(skip_input)
        advance_edge = advance_down and not self._advance_was_down
        skip_edge = skip_down and not self._skip_was_down
        self._advance_was_down = advance_down
        self._skip_was_down = skip_down
        if self.finished:
            return self.current_frame()
        if skip_edge:
            self.elapsed_seconds += dt
            self._beat_index = len(WHEELCHAIR_CHRIS_LEVEL_TWO_BEATS) - 1
            self._beat_elapsed = 0.0
            self._arrival_ready = True
            self._emitted.update({"finished"})
            return self.current_frame(("skipped", "finished"))
        self.elapsed_seconds += dt
        if self.beat_index == 0:
            was_ready = self._arrival_ready
            self._beat_elapsed += dt
            self._arrival_ready = self._beat_elapsed >= self.arrival_seconds
            if self._arrival_ready and not was_ready:
                return self.current_frame(self._emit_once("wheelchair_chris_settled"))
            if not self._arrival_ready:
                return self.current_frame()
            if advance_edge:
                return self.current_frame(self._advance_to_next_beat())
            return self.current_frame()
        self._beat_elapsed += dt
        if advance_edge:
            return self.current_frame(self._advance_to_next_beat())
        return self.current_frame()

    def reset(self) -> None:
        self.elapsed_seconds = 0.0
        self._emitted.clear()
        self._advance_was_down = False
        self._skip_was_down = False
        self._beat_index = 0
        self._beat_elapsed = 0.0
        self._arrival_ready = False


__all__ = [
    "JERRY_LEVEL_ONE_BEATS",
    "JerryLevelOneOutro",
    "LevelOutroFrame",
    "OutroBeat",
    "WHEELCHAIR_CHRIS_LEVEL_TWO_BEATS",
    "WheelchairChrisLevelTwoOutro",
]
