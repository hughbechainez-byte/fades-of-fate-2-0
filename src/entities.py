from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .animation_manifest import ANIMATION_PLAYBACK_HZ, clip_for, enemy_animation_actor
from .input_manager import InputSnapshot


# Combat simulation remains 60 Hz; pose selection is quantized to 30 Hz so
# both 30 and 60 FPS presentation observe the same ordered authored keys.
ANIMATION_TICKS_PER_SECOND = ANIMATION_PLAYBACK_HZ
_ANIMATION_PHASE_COUNT = 16
# Dave's twelve-pose gait now breathes slightly longer at the normal 126 px/s
# pace so the approved cels read as one carried stride instead of a shuffle.
# Shelly retains her existing quicker stride and authored timing.
_HERO_STRIDE_DISTANCE = 132.30
_SHELLY_STRIDE_DISTANCE = 84.0
_JERMAINE_STRIDE_DISTANCE = 132.0
_WHITE_DAVE_STRIDE_DISTANCE = 146.0
_CHIEF_STRIDE_DISTANCE = 140.0
_ENEMY_STRIDE_DISTANCE = 70.0
_COUCH_STRIDE_DISTANCE = 106.0
HIT_FLASH_SECONDS = 0.10
COUCH_RETREAT_STATES = frozenset({"bike_retreat", "bike_refuge", "bike_return"})
KO_LIGHTNING_STYLES: dict[
    str,
    tuple[str, tuple[int, int, int], float, float],
] = {
    "punch_1": ("ko_lightning_jab", (91, 226, 255), 38.0, 0.24),
    "punch_2": ("ko_lightning_cross", (191, 119, 255), 46.0, 0.27),
    "kick": ("ko_lightning_kick", (255, 218, 82), 52.0, 0.31),
    "super": ("ko_lightning_super", (178, 241, 255), 88.0, 0.22),
}


class AttackRouteStep(Protocol):
    """Narrow route boundary supplied by the gameplay route resolver."""

    route_id: str
    step_index: int
    step_id: str
    clip_id: str
    move_profile: Mapping[str, object]
    timing: Mapping[str, object]
    events: tuple[object, ...]


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    """Copy a route/move snapshot so later config edits cannot alter a swing."""

    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class AttackExecution:
    """The immutable gameplay/presentation contract captured at attack start."""

    route_id: str
    step_index: int
    step_id: str
    move_profile: Mapping[str, object]
    clip_id: str
    timing: Mapping[str, object]
    events: tuple[object, ...] = ()

    @classmethod
    def from_route_step(cls, step: AttackRouteStep) -> "AttackExecution":
        return cls(
            route_id=str(step.route_id),
            step_index=int(step.step_index),
            step_id=str(step.step_id),
            move_profile=_freeze_mapping(step.move_profile),
            clip_id=str(step.clip_id),
            timing=_freeze_mapping(step.timing),
            events=tuple(step.events),
        )

    @classmethod
    def legacy(cls, route_id: str, step_id: str, clip_id: str, move: Mapping[str, object]) -> "AttackExecution":
        frozen = _freeze_mapping(move)
        return cls(route_id, 0, step_id, frozen, clip_id, frozen, ())


def _animation_phase_offset(identity: int, state: str) -> float:
    """Return a stable sub-cycle offset without relying on randomized hash()."""

    state_salt = sum((index + 1) * ord(character) for index, character in enumerate(state))
    phase = (identity * 5 + state_salt) % _ANIMATION_PHASE_COUNT
    return phase / ANIMATION_TICKS_PER_SECOND


def _animation_tick(clock: float) -> int:
    # Fixed-step sums can land microscopically below an exact 30 Hz boundary.
    return int(max(0.0, clock) * ANIMATION_TICKS_PER_SECOND + 1e-6)


def _distance_animation_tick(
    distance: float,
    actor: str,
    state: str,
    stride_distance: float,
) -> int:
    """Map accumulated applied travel onto one complete authored gait cycle."""

    clip = clip_for(actor, state)
    timeline_ticks = clip.frame_count * max(1, clip.hold)
    cycles = max(0.0, distance) / max(1.0, stride_distance)
    return int(cycles * timeline_ticks + 1e-6)


def _hero_stride_distance(character: str) -> float:
    normalized = str(character).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"shelly", "shellie"}:
        return _SHELLY_STRIDE_DISTANCE
    if normalized == "jermaine":
        return _JERMAINE_STRIDE_DISTANCE
    if normalized == "white_dave":
        return _WHITE_DAVE_STRIDE_DISTANCE
    return _HERO_STRIDE_DISTANCE


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def move_toward(value: float, target: float, amount: float) -> float:
    if value < target:
        return min(target, value + amount)
    return max(target, value - amount)


def normalized(x: float, y: float) -> tuple[float, float]:
    length = math.hypot(x, y)
    if length <= 0.0001:
        return 0.0, 0.0
    return x / length, y / length


@dataclass(slots=True)
class Player:
    slot: int
    character: str
    binding: dict[str, object]
    x: float
    y: float
    config: dict[str, Any]
    moves: dict[str, Any]
    color_index: int = 0
    z: float = 0.0
    vz: float = 0.0
    facing: int = 1
    state: str = "idle"
    state_clock: float = 0.0
    state_duration: float = 0.0
    animation_clock: float = 0.0
    locomotion_distance: float = 0.0
    animation_state: str = ""
    health: float = 100.0
    max_health: float = 100.0
    lives: int = 3
    unlimited_lives: bool = False
    super_meter: float = 0.0
    chief_meter: float = 0.0
    bb_ammo: int = 0
    bb_cooldown: float = 0.0
    # Shelly's propane resource is deliberately separate from the shared
    # super meter.  Her super still calls Chief; Super Butane powers the
    # short-lived, high-output secondary flamethrower.
    super_butane_meter: float = 0.0
    propane_tick: float = 0.0
    invulnerable: float = 0.0
    combo_step: int = 0
    combo_style: str = "x"
    combo_grace: float = 0.0
    combo_repeat_lock: float = 0.0
    queued_light: bool = False
    queued_alt_light: bool = False
    queued_heavy: bool = False
    light_buffer_remaining: float = 0.0
    heavy_buffer_remaining: float = 0.0
    attack_connected: bool = False
    attack_fired: bool = False
    attack_hit_ids: set[tuple[str, int]] = field(default_factory=set)
    attack_hit_counts: dict[tuple[str, int], int] = field(default_factory=dict)
    attack_last_hit_times: dict[tuple[str, int], float] = field(default_factory=dict)
    attack_instance_sequence: int = 0
    attack_instance_id: int = 0
    # Captured when the attack state begins.  Rendering reads these values;
    # it must never call a move resolver that mutates combo_style.
    attack_animation_clip: str = "idle"
    attack_move_key: str = ""
    attack_timing_move: dict[str, Any] | None = None
    attack_execution: AttackExecution | None = None
    # Injected by the game after it validates the V2 route data against the
    # assembled V2 atlas.  It is intentionally optional for legacy save/test
    # construction, but Black Dave's live semantic controls require it.
    route_library: Any | None = None
    queued_route_action: str = ""
    route_buffer_remaining: float = 0.0
    # Air attacks alternate through a deterministic two-entry shuffle bag.
    # The bag is reset only on landing, so a jump can contain one attack.
    air_attack_bag: list[str] = field(default_factory=list)
    air_attack_seed: int = 0
    air_attack_used: bool = False
    air_attack_kind: str = ""
    # Previous active-window fist centre.  The combat engine uses this only
    # while an attack is active, so an old idle location cannot extend a fresh
    # strike after a state change.
    attack_sweep_x: float | None = None
    attack_sweep_y: float | None = None
    # Previous authoritative body sample for enemy attacks and projectiles.
    # This stays separate from the fist sample above: body motion and an
    # authored attack volume are different collision layers.
    hitbox_sweep_x: float | None = None
    hitbox_sweep_y: float | None = None
    hit_flash: float = 0.0
    dodge_vector: tuple[float, float] = (1.0, 0.0)
    down_timer: float = 0.0
    revive_progress: float = 0.0
    respawn_timer: float = 0.0
    score: int = 0
    hit_count: int = 0
    ko_count: int = 0
    last_input_vector: tuple[float, float] = (1.0, 0.0)
    idle_time: float = 0.0
    butane_timer: float = 8.0
    butane_anim: float = 0.0
    is_cpu: bool = False
    cpu_action_cooldown: float = 0.0
    cpu_heavy_cooldown: float = 0.0
    cpu_dodge_cooldown: float = 0.0
    cpu_idle_time: float = 0.0
    cpu_target_enemy_id: int = -1
    cpu_lane_offset: float = 0.0
    # Dave's ignition state is input-driven so it can be earned against empty
    # air just as reliably as during a crowded encounter.  The counter is
    # intentionally separate from the normal three-hit move combo.
    fist_flame_press_window: float = 0.0
    fist_flame_presses: int = 0
    flaming_fists_timer: float = 0.0
    flaming_fists_ignitions: int = 0
    jermaine_attack_count: int = 0
    jermaine_bark_cooldown: float = 0.0

    def __post_init__(self) -> None:
        global_cfg = self.config["global"]
        char_cfg = self.config[self.character]
        self.max_health = float(char_cfg.get("max_health", global_cfg["max_health"]))
        self.health = self.max_health
        self.lives = int(global_cfg["lives"])
        self.unlimited_lives = bool(global_cfg.get("unlimited_lives", False))
        self.butane_timer = random.uniform(7.0, 12.0)
        self._reset_animation_clock(self.state)

    @property
    def alive(self) -> bool:
        return self.state not in {"dead", "eliminated"}

    @property
    def combat_active(self) -> bool:
        return self.state not in {"dead", "eliminated", "downed"}

    @property
    def feet_y(self) -> float:
        return self.y

    def set_state(self, state: str, duration: float = 0.0) -> None:
        self.state = state
        self.state_clock = 0.0
        self.state_duration = duration
        self.attack_fired = False
        self.attack_connected = False
        self.attack_hit_ids.clear()
        self.attack_hit_counts.clear()
        self.attack_last_hit_times.clear()
        self.attack_sweep_x = None
        self.attack_sweep_y = None
        if state in {"light", "heavy", "air_attack", "super"}:
            self.attack_instance_sequence += 1
            self.attack_instance_id = self.attack_instance_sequence
            self.attack_animation_clip = self._animation_clip_for_state(state)
            self.attack_move_key = (
                self._combo_move_key()
                if state == "light" or (state == "heavy" and self.combo_style == "c")
                else "heavy"
                if state == "heavy"
                else state
            )
            if state == "light" or (state == "heavy" and self.combo_style == "c"):
                self.attack_timing_move = dict(self._combo_move())
            elif state == "heavy":
                self.attack_timing_move = dict(self.moves["heavy"])
            elif state == "air_attack":
                self.attack_timing_move = dict(self.moves["air"])
            else:
                self.attack_timing_move = None
            if self.attack_timing_move is not None:
                self.attack_execution = AttackExecution.legacy(
                    self.attack_move_key or state,
                    f"{self.attack_move_key or state}_legacy",
                    self.attack_animation_clip,
                    self.attack_timing_move,
                )
        else:
            self.attack_animation_clip = state
            self.attack_move_key = ""
            self.attack_timing_move = None
            self.attack_execution = None
        if state in {"hurt", "downed", "dead", "eliminated"}:
            # Damage is a hard combo interruption.  Retaining a queued edge
            # here caused one later button press to launch an unrequested
            # second strike after the player recovered.
            self.combo_step = 0
            self.combo_style = "x"
            self.combo_grace = 0.0
            self.queued_light = False
            self.queued_alt_light = False
            self.queued_heavy = False
            self.light_buffer_remaining = 0.0
            self.heavy_buffer_remaining = 0.0

    def begin_attack_execution(self, state: str, execution: AttackExecution) -> None:
        """Start a route-resolved attack without depending on route-loader internals."""

        timing = dict(execution.timing or execution.move_profile)
        self.set_state(state, self._move_total(timing))
        self.attack_execution = execution
        self.attack_animation_clip = execution.clip_id
        self.attack_move_key = execution.step_id
        self.attack_timing_move = dict(execution.move_profile)

    @staticmethod
    def _semantic_route_action(snapshot: InputSnapshot) -> str:
        """Resolve one physical V2 action edge without consulting legacy names."""

        for action in ("power", "kick", "regular"):
            if action in snapshot.pressed:
                return action
        return ""

    def _uses_v2_route_execution(self) -> bool:
        return self.attack_execution is not None and self.attack_execution.route_id in {"regular", "kick", "power"}

    def _begin_black_dave_v2_route(self, action: str, index: int, game: Any) -> None:
        """Capture the exact route step and its combat profile at button time."""

        if self.route_library is None:
            raise RuntimeError("Black Dave V2 route library was not installed")
        route_execution = self.route_library.capture_execution(action, index, metadata={"slot": self.slot})
        step = route_execution.step
        try:
            base_move = self.moves[step.move_table][step.move_index]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Black Dave V2 route references unavailable move {step.move_profile_id}") from exc
        move = dict(base_move)
        move.update({
            "startup": step.startup,
            "active": step.active,
            "recovery": step.recovery,
            "buffer_window": step.buffer_window,
            "cancel_start": step.cancel_start,
            "max_targets": step.target_cap,
            "v2_cancel_actions": tuple(step.cancel_actions),
            "v2_push_profile": step.push_profile,
            "v2_route_action": action,
            "v2_step_index": index,
        })
        timing = {
            name: move[name]
            for name in ("startup", "active", "recovery", "buffer_window", "cancel_start")
        }
        execution = AttackExecution(
            route_id=action,
            step_index=index,
            step_id=step.step_id,
            move_profile=_freeze_mapping(move),
            clip_id=step.clip_id,
            timing=_freeze_mapping(timing),
            events=tuple(step.animation_events) + tuple(step.vfx_events),
        )
        self.combo_style = {"regular": "z", "kick": "x", "power": "c"}[action]
        self.combo_step = index
        self.queued_route_action = ""
        self.route_buffer_remaining = 0.0
        self.begin_attack_execution("heavy" if action == "power" else "light", execution)
        game.audio.play_character(self.character, "grunt")

    def _try_begin_black_dave_v2_route(self, snapshot: InputSnapshot, game: Any) -> bool:
        """Bind Z/X/C semantic actions to the immutable three-by-seven plan."""

        action = self._semantic_route_action(snapshot)
        if self.character != "black_dave" or not action or self.route_library is None:
            return False
        if self.airborne:
            if action in {"regular", "kick", "power"}:
                self._start_air_attack()
                return True
            return False
        style = {"regular": "z", "kick": "x", "power": "c"}[action]
        if self.combo_repeat_lock > 0.0 and self.combo_style == style:
            return True
        self._begin_black_dave_v2_route(action, 0, game)
        return True

    def _update_black_dave_v2_route(self, snapshot: InputSnapshot, game: Any, dt: float) -> None:
        """Run a captured V2 step without rereading mutable combo configuration."""

        execution = self.attack_execution
        if execution is None:
            raise RuntimeError("V2 route state lost its immutable execution")
        move = self.attack_timing_move or dict(execution.move_profile)
        self.state_clock += dt
        self.route_buffer_remaining = max(0.0, self.route_buffer_remaining - dt)
        requested = self._semantic_route_action(snapshot)
        allowed = frozenset(map(str, move.get("v2_cancel_actions", ())))
        if requested and requested in allowed:
            self.queued_route_action = requested
            self.route_buffer_remaining = float(move.get("buffer_window", 0.0))

        active_start = float(move["startup"])
        active_end = active_start + float(move["active"])
        if active_start <= self.state_clock < active_end:
            first_active_sample = not self.attack_fired
            self.attack_fired = True
            hits = game.player_attack(
                self,
                move,
                self.state,
                already_hit=self.attack_hit_ids,
                hit_counts=self.attack_hit_counts,
                last_hit_times=self.attack_last_hit_times,
                attack_time=self.state_clock,
                play_whiff=first_active_sample,
            )
            self.attack_connected = self.attack_connected or hits > 0
            if first_active_sample and hits > 0 and execution.route_id == "power" and execution.step_index in {2, 4, 6}:
                game.apply_black_dave_v2_crowd_push(self, execution)

        cancel_start = float(move.get("cancel_start", self.state_duration))
        if self.state_clock >= max(active_end, cancel_start) and self.queued_route_action and self.route_buffer_remaining > 0.0:
            action = self.queued_route_action
            next_index = execution.step_index + 1 if action == execution.route_id else 0
            if next_index < 7:
                self._begin_black_dave_v2_route(action, next_index, game)
                return

        if self.state_clock < self.state_duration:
            return
        if execution.step_index == 6:
            self.combo_repeat_lock = max(
                self.combo_repeat_lock,
                float(self.config[self.character].get("combo_repeat_seconds", 5.0)),
            )
        self.queued_route_action = ""
        self.route_buffer_remaining = 0.0
        self.set_state("jump" if self.z > 0.0 else "idle")

    def gain_super(self, amount: float) -> float:
        """Award the character-tuned amount of Chief/Dave super meter.

        Shelly gains this meter faster so the CPU can call Chief's frenzy at
        useful moments without changing the global super threshold for Dave.
        """

        multiplier = max(0.0, float(self.config[self.character].get("super_gain_multiplier", 1.0)))
        before = self.super_meter
        self.super_meter = min(100.0, self.super_meter + max(0.0, float(amount)) * multiplier)
        return self.super_meter - before

    @property
    def animation_tick(self) -> int:
        if self.state == "walk":
            return _distance_animation_tick(
                self.locomotion_distance,
                self.character,
                "walk",
                _hero_stride_distance(self.character),
            )
        if self.state in {"jump", "air_attack", "jump_land"}:
            return _animation_tick(self.state_clock)
        return _animation_tick(self.animation_clock)

    @property
    def flaming_fists(self) -> bool:
        """Whether Black Dave currently carries the earned fire-fist bonus."""

        return self.character == "black_dave" and self.flaming_fists_timer > 0.0

    def fist_damage_multiplier(self) -> float:
        """Read the current fist-only bonus without changing ranged/super damage."""

        if not self.flaming_fists:
            return 1.0
        flames = self.config.get("black_dave", {}).get("fist_flames", {})
        return max(1.0, float(flames.get("damage_multiplier", 1.20)))

    def _reset_animation_clock(self, state: str) -> None:
        identity = self.slot * 17 + (7 if self.character == "shelly" else 1)
        self.animation_state = state
        self.animation_clock = _animation_phase_offset(identity, "idle")
        phase_fraction = (
            _animation_tick(_animation_phase_offset(identity, "walk"))
            % _ANIMATION_PHASE_COUNT
        ) / _ANIMATION_PHASE_COUNT
        self.locomotion_distance = phase_fraction * _hero_stride_distance(self.character)

    def advance_animation(self, dt: float) -> None:
        """Advance only presentation time; combat continues to use state_clock."""

        if self.state != self.animation_state:
            # Locomotion and idle each retain their own timeline.  A one-tick
            # obstruction or a short action therefore cannot restart a gait.
            self.animation_state = self.state
        if self.state == "idle":
            self.animation_clock += max(0.0, dt)

    def update(self, snapshot: InputSnapshot, game: Any, dt: float) -> None:
        self.hitbox_sweep_x = self.x
        self.hitbox_sweep_y = self.y
        global_cfg = self.config["global"]
        chief_cfg = game.data.get("chief", {})
        chief_meter_max = float(chief_cfg.get("command_meter_max", 100.0))
        self.chief_meter = min(
            chief_meter_max,
            self.chief_meter + float(chief_cfg.get("command_recharge_per_second", 7.0)) * dt,
        )
        self.invulnerable = max(0.0, self.invulnerable - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt / HIT_FLASH_SECONDS)
        self.bb_cooldown = max(0.0, self.bb_cooldown - dt)
        self.jermaine_bark_cooldown = max(0.0, self.jermaine_bark_cooldown - dt)
        self.combo_grace = max(0.0, self.combo_grace - dt)
        self.combo_repeat_lock = max(0.0, self.combo_repeat_lock - dt)
        self.light_buffer_remaining = max(0.0, self.light_buffer_remaining - dt)
        self.heavy_buffer_remaining = max(0.0, self.heavy_buffer_remaining - dt)
        if self.light_buffer_remaining <= 0.0:
            self.queued_light = False
        if self.heavy_buffer_remaining <= 0.0:
            self.queued_heavy = False
        self.butane_anim = max(0.0, self.butane_anim - dt)
        if self.character == "black_dave":
            self.fist_flame_press_window = max(0.0, self.fist_flame_press_window - dt)
            if self.fist_flame_press_window <= 0.0:
                self.fist_flame_presses = 0
            was_flaming = self.flaming_fists
            self.flaming_fists_timer = max(0.0, self.flaming_fists_timer - dt)
            if was_flaming and not self.flaming_fists:
                game.add_effect("text", self.x, self.y - 64, text="FISTS COOLED", color=(255, 189, 84), duration=0.65)
                game.log_breadcrumb("dave_fists_cooled", slot=self.slot + 1)

        if self.state == "eliminated":
            return
        if self.state == "dead":
            self.respawn_timer -= dt
            if self.respawn_timer <= 0.0 and (self.unlimited_lives or self.lives > 0):
                self.health = max(50.0, self.max_health * 0.60)
                self.x = max(60.0, game.camera_x + 100.0 + self.slot * 28.0)
                self.y = 268.0 + self.slot * 12.0
                self.invulnerable = 2.0
                self.set_state("idle")
                game.add_effect("text", self.x, self.y - 55, text="BACK IN!", color=(105, 235, 255))
            return
        if self.state == "downed":
            self.state_clock += dt
            self.down_timer -= dt
            if self.down_timer <= 0.0:
                if not self.unlimited_lives:
                    self.lives -= 1
                if not self.unlimited_lives and self.lives <= 0:
                    self.set_state("eliminated")
                else:
                    self.respawn_timer = 1.6
                    self.set_state("dead")
            return

        if self.state == "hurt":
            self.state_clock += dt
            if self.state_clock >= self.state_duration:
                self.set_state("idle")
            self._update_jump(game, dt)
            return

        if self.character == "black_dave" and snapshot.pressed & {"light", "alt_light", "heavy", "regular", "kick", "power"}:
            self._record_dave_flame_press(game)

        if self.state == "pet":
            self.state_clock += dt
            if self.state_clock >= self.state_duration:
                self.set_state("idle")
            return

        if self.state == "ranged":
            self.state_clock += dt
            if self.state_clock >= self.state_duration:
                self.set_state("idle")
            return

        if self.state == "jump_land":
            self.state_clock += dt
            if self.state_clock >= self.state_duration:
                self.set_state("idle")
            return

        if self.state == "propane":
            self._update_propane(snapshot, game, dt)
            return

        if self.state == "dodge":
            self.state_clock += dt
            if self.state_clock <= float(global_cfg["dodge_invulnerable"]):
                self.invulnerable = max(self.invulnerable, 0.06)
            speed = float(global_cfg["dodge_speed"])
            self._move_world(game, self.dodge_vector[0] * speed * dt, self.dodge_vector[1] * speed * 0.65 * dt)
            if self.state_clock >= self.state_duration:
                self.set_state("idle")
            return

        if self.state in {"light", "heavy", "air_attack", "super"}:
            if self._uses_v2_route_execution():
                self._update_black_dave_v2_route(snapshot, game, dt)
            else:
                self._update_attack(snapshot, game, dt)
            self._update_jump(game, dt)
            return

        if self.state == "jump":
            self.state_clock += dt
        self._update_jump(game, dt)
        move_x, move_y = normalized(snapshot.move_x, snapshot.move_y)
        if abs(move_x) + abs(move_y) > 0.05:
            self.last_input_vector = (move_x, move_y)
            if abs(move_x) > 0.05:
                self.facing = 1 if move_x > 0 else -1

        if "dodge" in snapshot.pressed:
            dodge_x, dodge_y = self.last_input_vector
            if abs(dodge_x) + abs(dodge_y) < 0.1:
                dodge_x = float(self.facing)
            self.dodge_vector = normalized(dodge_x, dodge_y)
            self.set_state("dodge", float(global_cfg["dodge_duration"]))
            game.audio.play("dodge")
            return

        if "super" in snapshot.pressed and self.super_meter >= float(global_cfg["super_cost"]):
            self.super_meter -= float(global_cfg["super_cost"])
            self.set_state("super", 0.82)
            game.audio.play_character(self.character, "grunt")
            game.log_breadcrumb("player_super", slot=self.slot + 1, character=self.character)
            return

        if self._try_begin_black_dave_v2_route(snapshot, game):
            return

        if "heavy" in snapshot.pressed and self.z <= 1.0:
            if self.combo_repeat_lock > 0.0 and self.combo_style == "c":
                return
            game.audio.play_character(self.character, "grunt")
            self.combo_style = "c"
            self.combo_step = self.combo_step if self.combo_grace > 0 else 0
            if game.try_throw(self):
                self.set_state("heavy", 0.52)
                self.attack_fired = True
            else:
                move = self._combo_move() if "heavy_combo" in self.moves else self.moves["heavy"]
                self.set_state("heavy", self._move_total(move))
            self._maybe_bark_as_jermaine(game)
            return

        if "alt_light" in snapshot.pressed:
            if self.airborne:
                self._start_air_attack()
            else:
                if self.combo_repeat_lock > 0.0 and self.combo_style == "z":
                    return
                self.combo_step = self.combo_step if self.combo_grace > 0 else 0
                self.combo_style = "z"
                self.set_state("light", self._move_total(self._alt_light_move()))
                self._maybe_bark_as_jermaine(game)
            return

        if "light" in snapshot.pressed:
            if self.airborne:
                self._start_air_attack()
            else:
                if self.combo_repeat_lock > 0.0 and self.combo_style == "x":
                    return
                self.combo_step = self.combo_step if self.combo_grace > 0 else 0
                self.combo_style = "x"
                self.set_state("light", self._move_total(self._light_move()))
                self._maybe_bark_as_jermaine(game)
            return

        if "jump" in snapshot.pressed and self.z <= 0.0:
            self._start_jump(game)

        speed_scale = float(self.config[self.character].get("speed_scale", 1.0))
        air_scale = 0.82 if self.z > 0.0 else 1.0
        applied_x, applied_y = self._move_world(
            game,
            move_x * float(global_cfg["x_speed"]) * speed_scale * air_scale * dt,
            move_y * float(global_cfg["y_speed"]) * speed_scale * air_scale * dt,
        )
        # Input can remain held against a rail, prop, or camera gate.  Animate
        # locomotion from actual displacement so blocked fighters do not run in
        # place or flicker between corrected positions.
        moving = abs(applied_x) + abs(applied_y) > 0.015
        if self.z <= 0.0:
            self.state = "walk" if moving else "idle"
            if moving:
                self.locomotion_distance += math.hypot(applied_x, applied_y)

        if moving or self.state != "idle":
            self.idle_time = 0.0
            self.butane_anim = 0.0
        else:
            self.idle_time += dt
            if self.character == "shelly" and self.idle_time > 2.5:
                self.butane_timer -= dt
                if self.butane_timer <= 0.0:
                    self.butane_anim = 2.4
                    self.butane_timer = random.uniform(9.0, 16.0)
                    game.add_effect("text", self.x, self.y - 58, text="*psssht*", color=(255, 214, 116))

    def _record_dave_flame_press(self, game: Any) -> None:
        """Track the six-press ignition and four-press sustain cadence.

        Six attack edges inside the authored window ignite the fists even when
        there is no target.  Once lit, only a fresh four-press burst renews
        the ten-second timer, so isolated taps do not make the effect endless.
        """

        flames = self.config.get("black_dave", {}).get("fist_flames", {})
        window_seconds = max(0.10, float(flames.get("press_window_seconds", 1.45)))
        activation_presses = max(6, int(flames.get("activation_presses", 6)))
        refresh_presses = max(4, int(flames.get("refresh_presses", 4)))
        active_seconds = max(0.10, float(flames.get("active_seconds", 10.0)))
        if self.fist_flame_press_window <= 0.0:
            self.fist_flame_presses = 0
        self.fist_flame_press_window = window_seconds
        self.fist_flame_presses += 1
        if not self.flaming_fists and self.fist_flame_presses >= activation_presses:
            self.flaming_fists_timer = active_seconds
            self.fist_flame_presses = 0
            self.fist_flame_press_window = 0.0
            self.flaming_fists_ignitions += 1
            game.add_effect("flame", self.x + self.facing * 18.0, self.y - 43.0, color=(255, 98, 35), radius=24, duration=0.52)
            game.add_effect("text", self.x, self.y - 66, text="FISTS IGNITED! +20%", color=(255, 205, 92), duration=0.82)
            game.audio.play("heavy")
            game.log_breadcrumb(
                "dave_fists_ignited",
                slot=self.slot + 1,
                presses=activation_presses,
                duration=round(active_seconds, 2),
            )
        elif self.flaming_fists and self.fist_flame_presses >= refresh_presses:
            self.flaming_fists_timer = active_seconds
            self.fist_flame_presses = 0
            self.fist_flame_press_window = 0.0
            game.add_effect("flame", self.x + self.facing * 18.0, self.y - 43.0, color=(255, 142, 45), radius=18, duration=0.22)
            game.log_breadcrumb("dave_fists_refreshed", slot=self.slot + 1, presses=refresh_presses)

    def _update_attack(self, snapshot: InputSnapshot, game: Any, dt: float) -> None:
        self.state_clock += dt
        if self.state == "super":
            if not self.attack_fired and self.state_clock >= 0.14:
                self.attack_fired = True
                game.activate_super(self)
            if self.state_clock >= self.state_duration:
                self.set_state("idle")
            return

        if self.state == "light":
            # Resolve the attack definition once at the state edge.  Reading
            # combo_step again on every frame could swap timing and hitboxes
            # underneath a pose that was already rendered.
            move = self.attack_timing_move or self._combo_move()
            if snapshot.pressed & {"light", "alt_light"}:
                self.queued_light = True
                self.light_buffer_remaining = float(move.get("buffer_window", 0.22))
            if "heavy" in snapshot.pressed and bool(move.get("heavy_cancel", True)):
                self.queued_heavy = True
                self.heavy_buffer_remaining = float(move.get("buffer_window", 0.22))
        elif self.state == "heavy":
            move = self.attack_timing_move or (
                self._combo_move()
                if self.combo_style == "c" and "heavy_combo" in self.moves
                else self.moves["heavy"]
            )
            if "heavy" in snapshot.pressed and self.combo_style == "c" and "heavy_combo" in self.moves:
                self.queued_heavy = True
                self.heavy_buffer_remaining = float(move.get("buffer_window", 0.22))
        else:
            move = self.attack_timing_move or self.moves["air"]

        active_start = float(move["startup"])
        active_end = active_start + float(move["active"])
        if active_start <= self.state_clock < active_end:
            first_active_sample = not self.attack_fired
            self.attack_fired = True
            hits = game.player_attack(
                self,
                move,
                self.state,
                already_hit=self.attack_hit_ids,
                hit_counts=self.attack_hit_counts,
                last_hit_times=self.attack_last_hit_times,
                attack_time=self.state_clock,
                play_whiff=first_active_sample,
            )
            self.attack_connected = self.attack_connected or hits > 0

        if self.state == "light":
            light_sequence = self._light_sequence()
            cancel_start = float(move.get("cancel_start", self.state_duration))
            can_chain = self.attack_connected or bool(move.get("chain_on_whiff", True))
            if self.state_clock >= max(active_end, cancel_start):
                if (
                    self.queued_heavy
                    and self.heavy_buffer_remaining > 0.0
                    and bool(move.get("heavy_cancel", True))
                ):
                    self.queued_light = False
                    self.queued_heavy = False
                    self.light_buffer_remaining = 0.0
                    self.heavy_buffer_remaining = 0.0
                    self.combo_step = 0
                    heavy = self.moves["heavy"]
                    self.set_state("heavy", self._move_total(heavy))
                    return
                if (
                    self.queued_light
                    and self.light_buffer_remaining > 0.0
                    and can_chain
                    and self.combo_step < len(light_sequence) - 1
                ):
                    self.combo_step += 1
                    self.queued_light = False
                    self.queued_heavy = False
                    self.light_buffer_remaining = 0.0
                    self.heavy_buffer_remaining = 0.0
                    self.combo_grace = float(move.get("combo_grace", 0.52))
                    next_move = self._combo_move()
                    self.set_state("light", self._move_total(next_move))
                    return
        elif self.state == "heavy" and self.combo_style == "c" and "heavy_combo" in self.moves:
            cancel_start = float(move.get("cancel_start", self.state_duration))
            can_chain = self.attack_connected or bool(move.get("chain_on_whiff", True))
            if self.state_clock >= max(active_end, cancel_start):
                if (
                    self.queued_heavy
                    and self.heavy_buffer_remaining > 0.0
                    and can_chain
                    and self.combo_step < len(self.moves["heavy_combo"]) - 1
                ):
                    self.queued_light = False
                    self.queued_heavy = False
                    self.light_buffer_remaining = 0.0
                    self.heavy_buffer_remaining = 0.0
                    self.combo_step += 1
                    self.combo_grace = float(move.get("combo_grace", 0.42))
                    next_move = self._combo_move()
                    self.set_state("heavy", self._move_total(next_move))
                    return

        if self.state_clock >= self.state_duration:
            light_sequence = self._light_sequence()
            if self.state == "light":
                self.combo_grace = float(move.get("combo_grace", 0.52))
                if self.combo_step >= len(light_sequence) - 1:
                    self.combo_step = 0
                    self.combo_repeat_lock = max(
                        self.combo_repeat_lock,
                        float(self.config[self.character].get("combo_repeat_seconds", 5.0)),
                    )
            elif self.state == "heavy":
                self.combo_grace = float(move.get("combo_grace", 0.42))
                if self.combo_style == "c" and "heavy_combo" in self.moves and self.combo_step >= len(self.moves["heavy_combo"]) - 1:
                    self.combo_step = 0
                    self.combo_repeat_lock = max(
                        self.combo_repeat_lock,
                        float(self.config[self.character].get("combo_repeat_seconds", 5.0)),
                    )
            self.queued_light = False
            self.queued_heavy = False
            self.light_buffer_remaining = 0.0
            self.heavy_buffer_remaining = 0.0
            self.set_state("jump" if self.z > 0 else "idle")

    def _maybe_bark_as_jermaine(self, game: Any) -> None:
        """Show Jermaine's recurring censored threat without spamming combat."""

        if self.character != "jermaine":
            return
        self.jermaine_attack_count += 1
        if self.jermaine_bark_cooldown > 0.0 or self.jermaine_attack_count % 3:
            return
        self.jermaine_bark_cooldown = 4.5
        phrase = "IMA F*** CUZ UP"
        game.add_effect(
            "text",
            self.x,
            self.y - 82.0,
            text=phrase,
            color=(255, 221, 106),
            duration=1.15,
        )
        game.log_breadcrumb("jermaine_combat_bark", player=self.slot + 1, phrase=phrase)

    def _update_propane(self, snapshot: InputSnapshot, game: Any, dt: float) -> None:
        """Sustain Shelly's costly secondary flame while the input is held."""

        cfg = game.data.get("shelly_propane", {})
        if self.character != "shelly" or "secondary" not in snapshot.held:
            self.set_state("idle")
            return
        if self.super_butane_meter <= 0.0:
            self.set_state("idle")
            return

        self.state_clock += dt
        self.super_butane_meter = max(
            0.0,
            self.super_butane_meter - max(0.0, float(cfg.get("drain_per_second", 100.0))) * dt,
        )
        interval = max(0.01, float(cfg.get("tick_seconds", 0.09)))
        self.propane_tick -= dt
        # Fixed simulation steps are normally much smaller than this interval,
        # but bounded catch-up keeps damage deterministic when a frame stalls.
        applications = 0
        while self.propane_tick <= 0.0 and applications < 4:
            game.apply_propane_flame(self)
            self.propane_tick += interval
            applications += 1
        if self.super_butane_meter <= 0.0:
            game.add_effect("text", self.x, self.y - 54, text="BUTANE OUT", color=(255, 174, 80), duration=0.55)
            self.set_state("idle")

    def _light_sequence(self) -> tuple[int, ...]:
        """Return character-specific indices into the shared light move table."""

        key = self._combo_move_key()
        sequence_key = {
            "light_combo": "light_combo_sequence",
            "alt_light_combo": "alt_light_combo_sequence",
            "heavy_combo": "heavy_combo_sequence",
            "heavy": "heavy_combo_sequence",
        }.get(key, "light_combo_sequence")
        configured = self.config[self.character].get(sequence_key)
        if key not in self.moves:
            key = "light_combo"
        if configured is None:
            return tuple(range(len(self.moves[key])))
        sequence = tuple(int(index) for index in configured)
        if not sequence or any(index < 0 or index >= len(self.moves[key]) for index in sequence):
            return tuple(range(len(self.moves[key])))
        return sequence

    def _combo_move_key(self) -> str:
        if self.combo_style == "z":
            return "alt_light_combo"
        if self.combo_style == "c":
            return "heavy_combo" if "heavy_combo" in self.moves else "heavy"
        return "light_combo"

    def _animation_clip_sequence(self, style: str) -> tuple[str, ...]:
        configured = self.config[self.character].get("animation_clip_sequences", {})
        sequence = configured.get(style) if isinstance(configured, dict) else None
        if isinstance(sequence, list) and sequence:
            return tuple(str(clip) for clip in sequence)
        if style == "c":
            return ("heavy", "heavy", "heavy", "heavy", "attack_4", "attack_4", "attack_4")
        if style == "z":
            return ("attack_2", "attack_1", "attack_4", "attack_3")
        return ("attack_1", "attack_2", "attack_3", "attack_4")

    def _animation_clip_for_state(self, state: str) -> str:
        if state == "light":
            sequence = self._animation_clip_sequence(self.combo_style)
            return sequence[min(max(0, self.combo_step), len(sequence) - 1)]
        if state == "heavy":
            sequence = self._animation_clip_sequence("c") if self.combo_style == "c" else ("heavy",)
            return sequence[min(max(0, self.combo_step), len(sequence) - 1)]
        return state

    def _combo_move(self) -> dict[str, Any]:
        move_key = self._combo_move_key()
        if self.combo_style == "c" and move_key == "heavy":
            return self.moves["heavy"]
        if move_key not in self.moves:
            move_key = "light_combo"
        sequence = self._light_sequence()
        chain_index = min(max(0, self.combo_step), len(sequence) - 1)
        return self.moves[move_key][sequence[chain_index]]

    def _light_move(self) -> dict[str, Any]:
        return self._combo_move()

    def _alt_light_move(self) -> dict[str, Any]:
        return self._combo_move()

    @staticmethod
    def _move_total(move: dict[str, Any]) -> float:
        return float(move["startup"]) + float(move["active"]) + float(move["recovery"])

    @property
    def airborne(self) -> bool:
        """True for actual ballistic travel, including the takeoff simulation tick."""

        return self.z > 0.001 or abs(self.vz) > 0.001

    def _start_jump(self, game: Any) -> None:
        self.z = max(0.0, self.z)
        self.vz = float(self.config["global"]["jump_velocity"])
        self.air_attack_used = False
        self.air_attack_kind = ""
        self.air_attack_bag.clear()
        self.air_attack_seed += 1
        self.set_state("jump")
        game.audio.play("jump")

    def _start_air_attack(self) -> bool:
        """Consume one deterministic punch/kick choice for the current jump."""

        if not self.airborne or self.air_attack_used:
            return False
        if not self.air_attack_bag:
            self.air_attack_bag = ["punch", "kick"]
            random.Random((self.slot + 1) * 1_000_003 + self.air_attack_seed).shuffle(self.air_attack_bag)
        kind = self.air_attack_bag.pop()
        move = dict(self.moves["air"])
        # Current manifests expose the common legacy air strip.  The selected
        # kind remains immutable in ``step_id`` and V2 glue can replace only
        # this clip id when its separately authored clips are registered.
        execution = AttackExecution.legacy("air", f"air_{kind}", "air_attack", move)
        self.air_attack_used = True
        self.air_attack_kind = kind
        self.begin_attack_execution("air_attack", execution)
        return True

    def _update_jump(self, game: Any, dt: float) -> None:
        if self.z <= 0.0 and self.vz <= 0.0:
            self.z = 0.0
            self.vz = 0.0
            self.air_attack_used = False
            self.air_attack_kind = ""
            self.air_attack_bag.clear()
            return
        self.vz -= float(self.config["global"]["gravity"]) * dt
        self.z += self.vz * dt
        if self.z <= 0.0:
            self.z = 0.0
            self.vz = 0.0
            self.air_attack_used = False
            self.air_attack_kind = ""
            self.air_attack_bag.clear()
            if self.state in {"jump", "air_attack"}:
                self.set_state("jump_land", 4.0 / ANIMATION_TICKS_PER_SECOND)
            game.audio.play("land")

    def _move_world(self, game: Any, dx: float, dy: float) -> tuple[float, float]:
        return game.move_actor(self, dx, dy)

    def take_damage(
        self,
        amount: float,
        game: Any,
        source: Any = None,
        *,
        hitstun: float = 0.34,
    ) -> bool:
        if not self.combat_active or self.invulnerable > 0.0:
            return False
        damage_taken = min(self.health, max(0.0, float(amount)))
        self.health = max(0.0, self.health - amount)
        self.hit_flash = 1.0
        record_damage = getattr(game, "record_player_damage", None)
        if callable(record_damage):
            record_damage(damage_taken)
        self.gain_super(2.0)
        game.audio.play("hurt")
        game.audio.play_character(
            self.character,
            "downed" if self.health <= 0.0 else "hurt",
        )
        game.add_effect("hit", self.x, self.y - self.z - 34, color=(255, 94, 78), radius=16, duration=0.18)
        game.add_effect("impact", self.x, self.y - self.z - 34, color=(255, 128, 102), radius=18, duration=0.20)
        game.add_effect("text", self.x, self.y - self.z - 58, text=f"-{int(round(amount))}", color=(255, 154, 130), duration=0.48)
        game.log_breadcrumb("player_hit", slot=self.slot + 1, damage=round(amount, 2), health=round(self.health, 2))
        alert_chief = getattr(game, "alert_chief", None)
        if callable(alert_chief):
            alert_chief(self, source)
        if self.health <= 0.0:
            self.down_timer = float(self.config["global"]["revive_window"])
            self.revive_progress = 0.0
            self.set_state("downed")
            game.add_effect("text", self.x, self.y - 58, text="REVIVE!", color=(255, 235, 95), duration=1.2)
        else:
            hurt_seconds = max(0.0, float(hitstun))
            self.invulnerable = max(0.56, hurt_seconds)
            self.set_state("hurt", hurt_seconds)
        return True

    def revive(self, game: Any) -> None:
        self.health = float(self.config["global"]["revive_health"])
        self.invulnerable = 1.2
        self.revive_progress = 0.0
        self.set_state("idle")
        game.audio.play("revive")
        game.add_effect("text", self.x, self.y - 58, text="UP!", color=(111, 255, 160))


@dataclass(slots=True)
class Enemy:
    enemy_id: int
    kind: str
    x: float
    y: float
    stats: dict[str, Any]
    variant_id: str = ""
    difficulty_scale: float = 1.0
    health: float = 1.0
    max_health: float = 1.0
    facing: int = -1
    state: str = "spawn"
    state_clock: float = 0.0
    state_duration: float = 0.45
    animation_clock: float = 0.0
    locomotion_distance: float = 0.0
    animation_state: str = ""
    cooldown: float = 0.0
    target_slot: int = -1
    token_held: int = 0
    attack_fired: bool = False
    attack_pattern: str = ""
    charge_vector: tuple[float, float] = (0.0, 0.0)
    knockback_vx: float = 0.0
    knockback_vy: float = 0.0
    wake_invulnerable: float = 0.0
    hit_flash: float = 0.0
    attack_instance_sequence: int = 0
    attack_instance_id: int = 0
    attack_hit_ids: set[tuple[str, int]] = field(default_factory=set)
    attack_hit_counts: dict[tuple[str, int], int] = field(default_factory=dict)
    attack_last_hit_times: dict[tuple[str, int], float] = field(default_factory=dict)
    burn_time: float = 0.0
    burn_tick: float = 0.0
    recent_damage_timer: float = 0.0
    ko_claimed: bool = False
    ko_hitter: Player | None = None
    ko_fall_seconds: float = 0.62
    ko_disappear_seconds: float = 0.22
    death_awarded: bool = False
    last_hitter: Player | None = None
    # Captured before each authoritative enemy update.  A player attack on the
    # following frame can resolve a target that crossed the punch lane between
    # the discrete samples instead of silently missing it.
    hitbox_sweep_x: float | None = None
    hitbox_sweep_y: float | None = None
    nav_detour_obstacle: str = ""
    nav_detour_depth: float | None = None
    nav_holding: bool = False
    couch_retreats_started: int = 0

    def __post_init__(self) -> None:
        self.max_health = float(self.stats["health"]) * self.difficulty_scale
        self.health = self.max_health
        self._reset_animation_clock(self.state)

    @property
    def alive(self) -> bool:
        return self.state != "dead"

    @property
    def targetable(self) -> bool:
        return (
            not self.ko_claimed
            and self.state not in {
                "dead",
                "spawn",
                "ko_dazed",
                "ko_fall",
                *COUCH_RETREAT_STATES,
            }
        )

    @property
    def feet_y(self) -> float:
        return self.y

    @property
    def animation_tick(self) -> int:
        if self.state == "chase":
            stride_distance = _COUCH_STRIDE_DISTANCE if self.kind in {"couch", "debo"} else _ENEMY_STRIDE_DISTANCE
            actor = (
                "couch"
                if self.kind in {"couch", "debo"}
                else enemy_animation_actor(self.kind, self.variant_id or None)
            )
            return _distance_animation_tick(
                self.locomotion_distance,
                actor,
                "walk",
                stride_distance,
            )
        return _animation_tick(self.animation_clock)

    def _reset_animation_clock(self, state: str) -> None:
        kind_salt = sum((index + 1) * ord(character) for index, character in enumerate(self.kind))
        identity = 1009 + self.enemy_id * 13 + kind_salt
        self.animation_state = state
        self.animation_clock = _animation_phase_offset(identity, "idle")
        stride_distance = _COUCH_STRIDE_DISTANCE if self.kind in {"couch", "debo"} else _ENEMY_STRIDE_DISTANCE
        phase_fraction = (
            _animation_tick(_animation_phase_offset(identity, "chase"))
            % _ANIMATION_PHASE_COUNT
        ) / _ANIMATION_PHASE_COUNT
        self.locomotion_distance = phase_fraction * stride_distance

    def advance_animation(self, dt: float) -> None:
        """Run idle art locally; chase phase comes from applied travel."""

        if self.state != self.animation_state:
            self.animation_state = self.state
        if self.state == "idle":
            self.animation_clock += max(0.0, dt)

    def update(self, game: Any, dt: float) -> None:
        self.hitbox_sweep_x = self.x
        self.hitbox_sweep_y = self.y
        self.cooldown = max(0.0, self.cooldown - dt)
        self.wake_invulnerable = max(0.0, self.wake_invulnerable - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt / HIT_FLASH_SECONDS)
        self.recent_damage_timer = max(0.0, self.recent_damage_timer - dt)
        if self.state == "ko_dazed":
            self.state_clock += dt
            if self.state_clock >= self.state_duration:
                self._set_state("ko_fall", self.ko_fall_seconds)
            return
        if self.state == "ko_fall":
            self.state_clock += dt
            if self.state_clock >= self.state_duration:
                self._die(game, self.ko_hitter)
            return
        if self.kind == "couch" and self.state in COUCH_RETREAT_STATES:
            # The game owns the add-wave roster and refuge coordinates. Couch
            # stays visibly airborne or beside the bikes while untargetable.
            update_retreat = getattr(game, "update_couch_retreat", None)
            if callable(update_retreat):
                update_retreat(self, dt)
            return
        if self.burn_time > 0.0 and self.state != "dead":
            self.burn_time -= dt
            self.burn_tick -= dt
            if self.burn_tick <= 0.0:
                self.burn_tick = 0.5
                burn_damage = 2.0
                retreat_health: float | None = None
                if self.kind == "couch":
                    next_retreat_health = getattr(game, "next_couch_retreat_health", None)
                    if callable(next_retreat_health):
                        candidate = next_retreat_health(self)
                        if (
                            candidate is not None
                            and self.health > candidate
                            and self.health - burn_damage <= candidate
                        ):
                            retreat_health = candidate
                            burn_damage = self.health - candidate
                self.health -= burn_damage
                game.add_effect("ember", self.x, self.y - 38, color=(255, 130, 40))
                if retreat_health is not None:
                    start_retreat = getattr(game, "start_couch_retreat", None)
                    if callable(start_retreat):
                        start_retreat(self)
                elif self.health <= 0:
                    self._die(game, self.last_hitter)
                if self.state in COUCH_RETREAT_STATES:
                    return

        if self.state == "dead":
            self.state_clock += dt
            return
        if self.state == "spawn":
            self.state_clock += dt
            if self.state_clock >= self.state_duration:
                self._set_state("chase")
            return
        if self.state == "hitstun":
            self.state_clock += dt
            game.move_actor(self, self.knockback_vx * dt, self.knockback_vy * dt)
            self.knockback_vx = move_toward(self.knockback_vx, 0.0, 180.0 * dt)
            self.knockback_vy = move_toward(self.knockback_vy, 0.0, 150.0 * dt)
            if self.state_clock >= self.state_duration:
                self._set_state("chase")
            return
        if self.state == "down":
            self.state_clock += dt
            game.move_actor(self, self.knockback_vx * dt, self.knockback_vy * dt)
            self.knockback_vx = move_toward(self.knockback_vx, 0.0, 130.0 * dt)
            self.knockback_vy = move_toward(self.knockback_vy, 0.0, 110.0 * dt)
            if self.state_clock >= self.state_duration:
                physics = game.data.get("engine", {}).get("physics", {})
                self.wake_invulnerable = max(
                    self.wake_invulnerable,
                    float(physics.get("enemy_wakeup_invulnerability", 0.18)),
                )
                self._set_state("chase")
            return
        if self.kind == "debo" and self.state == "guard":
            self.state_clock += dt
            target = game.nearest_player(self.x, self.y)
            if target is not None:
                dx = self.x - target.x
                dy = self.y - target.y
                nx, ny = normalized(dx, dy)
                speed = 112.0
                applied_x, applied_y = game.move_actor(self, nx * speed * dt, ny * speed * 0.52 * dt)
                if abs(applied_x) + abs(applied_y) > 0.015:
                    self.locomotion_distance += math.hypot(applied_x, applied_y)
                self.facing = 1 if dx >= 0 else -1
            if self.state_clock >= self.state_duration:
                self._finish_attack(game)
            return
        if self.state == "windup":
            self.state_clock += dt
            if self.state_clock >= self.state_duration:
                self._execute_attack(game)
            return
        if self.state == "charge":
            self.state_clock += dt
            speed = 205.0 if self.kind == "cart" else 140.0 if self.kind == "debo" else 168.0
            game.move_actor(
                self,
                self.charge_vector[0] * speed * dt,
                self.charge_vector[1] * speed * 0.52 * dt,
            )
            landed = game.enemy_attack(
                self,
                range_x=30,
                range_y=18,
                damage=float(self.stats["damage"]),
                already_hit=self.attack_hit_ids,
                hit_counts=self.attack_hit_counts,
                last_hit_times=self.attack_last_hit_times,
                attack_time=self.state_clock,
            )
            self.attack_fired = self.attack_fired or landed
            if self.state_clock >= self.state_duration:
                self._enter_recovery()
            return
        if self.state == "attack":
            self.state_clock += dt
            if self.attack_pattern in {"glass_bottle", "bike_tire", "taser"}:
                # The projectile is emitted on the first authored active cel.
                # Hold that cel family for the configured active interval so
                # the hand release and the separate projectile remain one
                # continuous action instead of jumping from windup to recovery.
                if self.state_clock >= self.state_duration:
                    self._enter_recovery()
                return
            landed = game.enemy_attack(
                self,
                range_x=self._melee_reach(),
                range_y=float(self.stats["depth_range"]) + 3.0,
                damage=float(self.stats["damage"]),
                already_hit=self.attack_hit_ids,
                hit_counts=self.attack_hit_counts,
                last_hit_times=self.attack_last_hit_times,
                attack_time=self.state_clock,
            )
            self.attack_fired = self.attack_fired or landed
            if self.state_clock >= self.state_duration:
                self._enter_recovery()
            return
        if self.state == "recovery":
            self.state_clock += dt
            if self.state_clock >= self.state_duration:
                self._finish_attack(game)
            return

        target = game.nearest_player(self.x, self.y)
        if target is None:
            # Losing the target is a real locomotion stop, not permission to
            # keep displaying the last chase loop in place.
            self.state = "idle"
            return
        self.target_slot = target.slot
        dx = target.x - self.x
        dy = target.y - self.y
        self.facing = 1 if dx >= 0 else -1
        attack_style = str(self.stats.get("attack_style", self.kind))
        ranged_attack = attack_style in {"pipe", "glass_bottle", "bike_tire", "taser"}
        desired_x = float(self.stats["attack_range"]) * (0.88 if ranged_attack else 0.75)
        within_x = abs(dx) <= float(self.stats["attack_range"])
        within_y = abs(dy) <= float(self.stats["depth_range"])
        if within_x and within_y and self.cooldown <= 0.0:
            cost = int(self.stats.get("token_cost", 1))
            if game.acquire_attack_token(self, cost):
                self.token_held = cost
                self._begin_attack(game, target)
                return

        speed = float(self.stats["speed"])
        move_x = 0.0
        move_y = 0.0
        hold_hysteresis_x = float(game.data["engine"]["physics"].get("enemy_hold_hysteresis_x", 8.0))
        hold_hysteresis_depth = float(game.data["engine"]["physics"].get("enemy_hold_hysteresis_depth", 5.0))
        too_close = (ranged_attack or self.kind == "whip") and abs(dx) < desired_x * 0.55
        if self.nav_holding:
            self.nav_holding = (
                not too_close
                and abs(dx) <= float(self.stats["attack_range"]) + hold_hysteresis_x
                and abs(dy) <= float(self.stats["depth_range"]) + hold_hysteresis_depth
            )
        elif within_x and within_y and not too_close:
            # Keep a stable contact/attack position while cooling down or
            # waiting for an attack token. Re-approaching through the crowd
            # solver every tick is the main source of visible correction jitter.
            self.nav_holding = True

        if self.nav_holding:
            self.state = "idle"
            return

        if abs(dy) > max(6.0, float(self.stats["depth_range"]) * 0.7):
            move_y = clamp(dy, -1.0, 1.0) * speed * 0.72 * dt
        if abs(dx) > desired_x:
            move_x = clamp(dx, -1.0, 1.0) * speed * dt
        elif too_close:
            move_x = -clamp(dx, -1.0, 1.0) * speed * 0.55 * dt
        applied_x, applied_y = game.move_enemy_toward(self, target, move_x, move_y, dt)
        self.state = "chase" if abs(applied_x) + abs(applied_y) > 0.015 else "idle"
        if self.state == "chase":
            self.locomotion_distance += math.hypot(applied_x, applied_y)

    def _begin_attack(self, game: Any, target: Player) -> None:
        self.nav_holding = False
        self.attack_fired = False
        self.attack_instance_sequence += 1
        self.attack_instance_id = self.attack_instance_sequence
        self.attack_hit_ids.clear()
        self.attack_hit_counts.clear()
        self.attack_last_hit_times.clear()
        self.attack_pattern = str(self.stats.get("attack_style", self.kind))
        if self.kind == "couch":
            roll = random.random()
            if self.health < self.max_health * 0.55 and roll < 0.44:
                self.attack_pattern = "pump"
            elif roll < 0.68:
                self.attack_pattern = "laugh"
            else:
                self.attack_pattern = "stick"
        elif self.kind == "debo":
            distance = math.hypot(target.x - self.x, (target.y - self.y) * 1.25)
            roll = random.random()
            if distance > 96.0 or (self.health < self.max_health * 0.58 and roll < 0.48):
                self.attack_pattern = "debo_charge"
            elif distance < 52.0 or roll < 0.34:
                self.attack_pattern = "debo_swing"
            else:
                self.attack_pattern = "debo_guard"
        if self.kind == "cart" or self.attack_pattern == "pump":
            self.charge_vector = normalized(target.x - self.x, target.y - self.y)
        duration = float(self.stats["windup"])
        if self.attack_pattern == "laugh":
            duration = 0.72
            game.audio.play("laugh")
            game.add_effect("text", self.x, self.y - 58, text="HA HA HA!", color=(255, 180, 239), duration=0.9)
        self._set_state("windup", duration)

    def _execute_attack(self, game: Any) -> None:
        if self.kind == "cart" or self.attack_pattern == "pump":
            self.attack_fired = False
            self._set_state(
                "charge",
                float(
                    self.stats.get(
                        "charge_active",
                        0.52 if self.kind == "cart" else 0.68,
                    )
                ),
            )
            return
        if self.kind == "pipe":
            target = game.player_by_slot(self.target_slot)
            if target is not None:
                game.spawn_pipe(self, target)
            self.attack_fired = True
            self._enter_recovery()
        elif self.attack_pattern in {"glass_bottle", "bike_tire", "taser"}:
            target = game.player_by_slot(self.target_slot)
            if target is not None:
                game.spawn_enemy_projectile(self, target, self.attack_pattern)
            self._set_state("attack", float(self.stats["active"]))
            self.attack_fired = True
        elif self.kind == "debo" and self.attack_pattern == "debo_guard":
            self.attack_fired = False
            self._set_state("guard", max(0.42, float(self.stats["active"]) * 1.1))
        elif self.attack_pattern == "laugh":
            game.add_effect("shock", self.x, self.y, radius=45, color=(255, 120, 210), duration=0.38)
            self.attack_fired = True
            self._enter_recovery()
        else:
            # Melee damage now exists for the authored active interval instead
            # of being a single query at the windup/recovery boundary.
            self._set_state("attack", float(self.stats["active"]))

    def _melee_reach(self) -> float:
        return (
            76.0 if self.kind == "whip"
            else 58.0 if self.kind == "couch"
            else 54.0 if self.kind == "debo"
            else 46.0 if self.kind == "police"
            else 42.0 if self.kind == "security"
            else 34.0
        )

    def _enter_recovery(self) -> None:
        self._set_state("recovery", float(self.stats["recovery"]))

    def _finish_attack(self, game: Any) -> None:
        game.release_attack_token(self)
        self.token_held = 0
        self.cooldown = float(self.stats["cooldown"])
        self._set_state("chase")

    def _set_state(self, state: str, duration: float = 0.0) -> None:
        self.state = state
        self.state_clock = 0.0
        self.state_duration = duration
        self.attack_fired = False

    def take_damage(
        self,
        amount: float,
        game: Any,
        hitter: Player | None,
        *,
        hitstun: float = 0.25,
        knockback: float = 12.0,
        knockdown: bool = False,
        burn: bool = False,
        feedback: bool = True,
        recoil_pixels: float = 0.0,
    ) -> bool:
        if not self.targetable:
            return False
        applied_amount = max(0.0, float(amount))
        retreat_health: float | None = None
        if self.kind == "couch":
            next_retreat_health = getattr(game, "next_couch_retreat_health", None)
            if callable(next_retreat_health):
                retreat_health = next_retreat_health(self)
                if (
                    retreat_health is not None
                    and self.health > retreat_health
                    and self.health - applied_amount <= retreat_health
                ):
                    # A large hit cannot erase either authored boss phase. Only
                    # the damage up to this health gate is applied and scored.
                    applied_amount = self.health - retreat_health
                else:
                    retreat_health = None
        elif self.kind == "debo" and self.state == "guard":
            applied_amount *= 0.72
        game.release_attack_token(self)
        self.token_held = 0
        self.health -= applied_amount
        self.hit_flash = 1.0
        quiet_seconds = float(
            game.data.get("ko_companion", {}).get("recent_damage_seconds", 0.9)
        )
        self.recent_damage_timer = max(self.recent_damage_timer, quiet_seconds)
        self.last_hitter = hitter or self.last_hitter
        if hitter is not None:
            game.award_hit(hitter, self, applied_amount)
        direction = 1 if hitter is None or self.x >= hitter.x else -1
        base_velocity = knockback * 4.0
        if recoil_pixels > 0.0:
            # Convert a requested visible recoil distance into the minimum
            # velocity for the existing 180 px/s² hitstun deceleration.
            base_velocity = max(base_velocity, math.sqrt(2.0 * 180.0 * recoil_pixels))
        self.knockback_vx = direction * base_velocity
        self.knockback_vy = (
            0.0
            if hitter is None
            else clamp(self.y - hitter.y, -1.0, 1.0) * knockback * 1.25
        )
        if burn:
            self.burn_time = max(self.burn_time, 2.2)
            self.burn_tick = 0.35
        if feedback:
            impact_color = (255, 128, 48) if burn else ((255, 239, 142) if knockdown else (255, 231, 92))
            game.add_effect(
                "hit",
                self.x,
                self.y - 35,
                color=impact_color,
                radius=20 if knockdown else 15,
                duration=0.18,
                direction=direction,
                _start_paused=True,
            )
            game.add_effect(
                "impact",
                self.x,
                self.y - 35,
                color=impact_color,
                radius=24 if knockdown else 18,
                duration=0.20,
                direction=direction,
                _start_paused=True,
            )
            game.add_effect(
                "text",
                self.x,
                self.y - 57,
                text=f"-{int(round(applied_amount))}",
                color=impact_color,
                duration=0.48,
                _start_paused=True,
            )
            game.audio.play("heavy_hit" if knockdown else "hit")
            game.audio.play("enemy_downed" if self.health <= 0.0 else "enemy_grunt")
        if retreat_health is not None:
            start_retreat = getattr(game, "start_couch_retreat", None)
            if callable(start_retreat) and start_retreat(self):
                return True
        if self.health <= 0.0:
            self._die(game, hitter)
        elif knockdown:
            self._set_state("down", max(0.52, hitstun))
        else:
            self._set_state("hitstun", hitstun)
        return True

    def begin_ko_sequence(
        self,
        game: Any,
        hitter: Player | None,
        *,
        daze_seconds: float,
        fall_seconds: float,
        disappear_seconds: float = 0.22,
    ) -> bool:
        """Start KO's authored daze/fall finish without boss health clamping."""

        if (
            not self.alive
            or self.state in {"spawn", "ko_dazed", "ko_fall", *COUCH_RETREAT_STATES}
            or (not self.targetable and not self.ko_claimed)
        ):
            return False
        remaining_health = max(0.0, self.health)
        game.release_attack_token(self)
        self.token_held = 0
        self.health = 0.0
        self.ko_claimed = False
        self.ko_hitter = hitter
        self.last_hitter = hitter or self.last_hitter
        self.burn_time = 0.0
        self.burn_tick = 0.0
        self.recent_damage_timer = 0.0
        self.knockback_vx = 0.0
        self.knockback_vy = 0.0
        self.hit_flash = 1.0
        self.ko_fall_seconds = max(0.05, float(fall_seconds))
        self.ko_disappear_seconds = max(0.05, float(disappear_seconds))
        if hitter is not None:
            game.award_hit(hitter, self, remaining_health)
        self._set_state("ko_dazed", max(0.10, float(daze_seconds)))
        game.add_effect(
            "impact",
            self.x,
            self.y - 36.0,
            color=(255, 231, 92),
            radius=26.0,
            duration=0.22,
        )
        game.audio.play("heavy")
        game.audio.play("enemy_downed")
        game.log_breadcrumb(
            "ko_companion_dazed_enemy",
            enemy=self.kind,
            enemy_id=self.enemy_id,
            boss=self.kind in {"couch", "debo"},
        )
        return True

    def _die(self, game: Any, hitter: Player | None) -> None:
        if self.state == "dead":
            return
        game.release_attack_token(self)
        self.token_held = 0
        self.ko_claimed = False
        self.health = 0.0
        dead_seconds = self.ko_disappear_seconds if self.ko_hitter is not None else 0.72
        self._set_state("dead", dead_seconds)
        self.knockback_vx *= 1.2
        if not self.death_awarded:
            self.death_awarded = True
            game.enemy_defeated(self, hitter)


@dataclass(slots=True)
class Chief:
    owner: Player
    config: dict[str, Any]
    x: float
    y: float
    frenzy: float = 0.0
    attack_cooldown: float = 1.0
    facing: int = 1
    state: str = "follow"
    bite_flash: float = 0.0
    pursuit_timer: float = 0.0
    protect_enemy_id: int = -1
    protect_target: Enemy | None = None
    pet_timer: float = 0.0
    pet_cooldown: float = 4.0
    pet_partner: Player | None = None
    command_enemy_id: int = -1
    command_target: Enemy | None = None
    command_caller: Player | None = None
    command_return_pending: bool = False
    # ``maul`` is a short bite hold over the exact encounter-roster target that
    # Chief floored. It deliberately does not add extra damage ticks.
    maul_timer: float = 0.0
    maul_target_id: int = -1
    maul_target: Enemy | None = None
    animation_clock: float = 0.0
    locomotion_distance: float = 0.0
    animation_state: str = ""
    animation_moving: bool = False

    def __post_init__(self) -> None:
        self._reset_animation_clock(self.visual_animation_state)

    @property
    def feet_y(self) -> float:
        return self.y

    @property
    def visual_animation_state(self) -> str:
        """Resolve behavior into art without showing travel while blocked."""

        if self.maul_timer > 0.0:
            return "maul"
        if self.bite_flash > 0.0:
            return "attack"
        if self.frenzy > 0.0:
            return "frenzy"
        if self.state == "command":
            return "command" if self.animation_moving else "guard"
        if self.state in {"return_to_caller", "follow"}:
            return "move" if self.animation_moving else "idle"
        if self.state in {"hunt", "protect"}:
            return "move" if self.animation_moving else "guard"
        if self.state == "pet" and self.animation_moving:
            return "move"
        return self.state

    @property
    def animation_tick(self) -> int:
        if self.visual_animation_state in {"move", "command"}:
            return _distance_animation_tick(
                self.locomotion_distance,
                "chief",
                "move",
                _CHIEF_STRIDE_DISTANCE,
            )
        return _animation_tick(self.animation_clock)

    def _reset_animation_clock(self, state: str) -> None:
        identity = 2003 + self.owner.slot * 17
        self.animation_state = state
        self.animation_clock = _animation_phase_offset(identity, "idle")
        phase_fraction = (
            _animation_tick(_animation_phase_offset(identity, "move"))
            % _ANIMATION_PHASE_COUNT
        ) / _ANIMATION_PHASE_COUNT
        self.locomotion_distance = phase_fraction * _CHIEF_STRIDE_DISTANCE

    def advance_animation(self, dt: float) -> None:
        """Advance Chief's non-travel loop; gait phase comes from displacement."""

        visual_state = self.visual_animation_state
        if visual_state != self.animation_state:
            if visual_state not in {"idle", "move", "command", "guard"}:
                self.animation_clock = 0.0
            self.animation_state = visual_state
        if visual_state not in {"move", "command"}:
            self.animation_clock += max(0.0, dt)

    def _record_animation_motion(self, applied_x: float, applied_y: float) -> None:
        self.animation_moving = abs(applied_x) + abs(applied_y) > 0.015
        if self.animation_moving:
            self.locomotion_distance += math.hypot(applied_x, applied_y)

    @staticmethod
    def _live_roster_enemy(game: Any, target: Any) -> Enemy | None:
        """Return ``target`` only while that exact live object is in the roster."""

        if target is None or not getattr(target, "targetable", False):
            return None
        return next(
            (enemy for enemy in getattr(game, "enemies", ()) if enemy is target),
            None,
        )

    def _nearest_live_roster_enemy(self, game: Any, x: float, y: float) -> Enemy | None:
        """Select deterministically from current encounter objects, never IDs."""

        candidates = [
            enemy
            for enemy in getattr(game, "enemies", ())
            if getattr(enemy, "targetable", False)
        ]
        return min(
            candidates,
            key=lambda enemy: (
                abs(enemy.x - x) + abs(enemy.y - y) * 1.8,
                enemy.enemy_id,
            ),
            default=None,
        )

    def _clear_maul(self) -> None:
        self.maul_timer = 0.0
        self.maul_target_id = -1
        self.maul_target = None

    def activate_frenzy(self, seconds: float, game: Any) -> None:
        if self.pet_partner is not None and self.pet_partner.state == "pet":
            self.pet_partner.set_state("idle")
        self.pet_partner = None
        self.pet_timer = 0.0
        self._clear_command()
        self.frenzy = max(self.frenzy, seconds)
        self.attack_cooldown = 0.0
        self.state = "frenzy"
        self.animation_moving = False
        game.add_effect("text", self.x, self.y - 38, text="CHIEF!", color=(255, 224, 86))

    def protect(self, enemy: Any) -> None:
        """Prioritize an enemy that just threatened Dave or Shelly."""

        enemy_id = getattr(enemy, "enemy_id", -1)
        if enemy_id >= 0:
            self.protect_enemy_id = int(enemy_id)
            self.protect_target = enemy
            self.pursuit_timer = max(self.pursuit_timer, 2.4)
            self.attack_cooldown = min(self.attack_cooldown, 0.18)

    def start_command(self, caller: Player, target: Any, game: Any) -> bool:
        """Send Chief at one caller-selected target without starting frenzy."""

        target = self._live_roster_enemy(game, target)
        enemy_id = int(getattr(target, "enemy_id", -1))
        if (
            enemy_id < 0
            or self.frenzy > 0.0
        ):
            return False
        retargeted = self.command_caller is not None
        if self.pet_partner is not None and self.pet_partner.state == "pet":
            self.pet_partner.set_state("idle")
        self.pet_partner = None
        self.pet_timer = 0.0
        self.command_enemy_id = enemy_id
        self.command_target = target
        self.command_caller = caller
        self.command_return_pending = False
        self.state = "command"
        self.animation_moving = False
        self.attack_cooldown = 0.0
        self.facing = 1 if target.x >= self.x else -1
        game.add_effect("text", caller.x, caller.y - 54, text="CHIEF!", color=(255, 220, 73), duration=0.65)
        game.log_breadcrumb(
            "chief_commanded",
            player=caller.slot + 1,
            enemy_id=enemy_id,
            retargeted=retargeted,
        )
        return True

    def start_pet(self, partner: Player, game: Any, *, seconds: float = 0.9, force: bool = False) -> bool:
        """Enter a short calm interaction with a safe command caller."""

        if self.frenzy > 0.0 or self.pet_timer > 0.0 or (self.pet_cooldown > 0.0 and not force):
            return False
        self.pet_partner = partner
        self.pet_timer = seconds
        self.pet_cooldown = float(self.config.get("pet_cooldown", 9.0))
        self.state = "pet"
        self.animation_moving = False
        partner.set_state("pet", seconds)
        partner.facing = 1 if self.x >= partner.x else -1
        game.add_effect("text", (self.x + partner.x) * 0.5, min(self.y, partner.y) - 42, text="GOOD BOY!", color=(255, 224, 108), duration=0.75)
        game.log_breadcrumb("chief_petted", player=partner.slot + 1)
        return True

    def update(self, game: Any, dt: float) -> None:
        self.animation_moving = False
        self.bite_flash = max(0.0, self.bite_flash - dt)
        self.maul_timer = max(0.0, self.maul_timer - dt)
        if self.maul_timer <= 0.0 and self.maul_target is not None:
            self._clear_maul()
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        self.pursuit_timer = max(0.0, self.pursuit_timer - dt)
        self.pet_cooldown = max(0.0, self.pet_cooldown - dt)
        party_active = any(player.combat_active for player in getattr(game, "players", ()))
        if not party_active and self.command_caller is None and self.frenzy <= 0.0:
            return
        self.frenzy = max(0.0, self.frenzy - dt)

        if self.maul_timer > 0.0:
            # The target remains the actual downed roster object. If another
            # attack finishes it or the encounter removes it, cancel the hold
            # immediately and let frenzy select another live enemy below.
            target = self._live_roster_enemy(game, self.maul_target)
            if target is not None and target.state == "down":
                self.facing = 1 if target.x >= self.x else -1
                self.state = "maul"
                return
            self._clear_maul()

        # A camera transition or long pursuit must not strand Chief in another
        # part of the stage. Commands perform the same check synchronously, so
        # pressing Call Chief during hitstop also brings him back immediately.
        if self.frenzy <= 0.0:
            keep_with_party = getattr(game, "keep_chief_with_party", None)
            if callable(keep_with_party):
                keep_with_party(self)

        target = self._nearest_live_roster_enemy(game, self.x, self.y)
        if self.frenzy > 0.0:
            if target is not None:
                self.state = "frenzy"
                dx, dy = target.x - self.x, target.y - self.y
                nx, ny = normalized(dx, dy)
                self.facing = 1 if dx >= 0 else -1
                speed = float(self.config["frenzy_speed"])
                applied_x, applied_y = game.move_actor(self, nx * speed * dt, ny * speed * 0.68 * dt)
                self._record_animation_motion(applied_x, applied_y)
                if abs(dx) < 25 and abs(dy) < 16 and self.attack_cooldown <= 0.0:
                    landed = target.take_damage(
                        float(self.config["frenzy_damage"]), game, self.owner,
                        hitstun=0.22, knockback=16.0, knockdown=True,
                    )
                    if landed:
                        self.attack_cooldown = float(self.config["frenzy_cooldown"])
                        self.bite_flash = 0.22
                        self._start_maul(target, game)
                        game.audio.play("chief_bite")
                return

            # A cleared street should not leave Chief's timer burning through
            # the walk to the next encounter. Retain a short victorious pose
            # while queued enemies still arrive, then settle so the next real
            # crowd can earn Shelly's second frenzy naturally.
            if not getattr(game, "spawn_queue", ()):
                linger = max(0.0, float(self.config.get("frenzy_clear_linger_seconds", 0.42)))
                self.frenzy = min(self.frenzy, linger)
            self.state = "frenzy"
            self.animation_moving = False
            return

        if self._update_command(game, dt):
            return

        if self.pet_timer > 0.0 and self.pet_partner is not None and self.pet_partner.combat_active:
            self.pet_timer = max(0.0, self.pet_timer - dt)
            self.state = "pet"
            target_x = self.pet_partner.x + self.pet_partner.facing * 23.0
            target_y = self.pet_partner.y + 8.0
            dx, dy = target_x - self.x, target_y - self.y
            nx, ny = normalized(dx, dy)
            if abs(dx) + abs(dy) > 3.0:
                applied_x, applied_y = game.move_actor(self, nx * 118.0 * dt, ny * 82.0 * dt)
                self._record_animation_motion(applied_x, applied_y)
            self.facing = -self.pet_partner.facing
            if self.pet_timer <= 0.0:
                self.pet_partner = None
                self.state = "follow"
            return

        # Stay anchored to Shelly, but intercept threats to either Shelly or Dave.
        protected_target = self._live_roster_enemy(game, self.protect_target)
        dave = next((player for player in game.players if player.character == "black_dave" and player.combat_active), None)
        owner_threat = self._nearest_live_roster_enemy(game, self.owner.x, self.owner.y)
        dave_threat = self._nearest_live_roster_enemy(game, dave.x, dave.y) if dave is not None else None
        guard_radius = float(self.config.get("guard_radius", 105.0))
        roam_radius = float(self.config.get("autonomous_radius", 155.0))
        max_roam = float(self.config.get("max_roam_from_shelly", 185.0))
        distance_from_owner = math.hypot(self.x - self.owner.x, (self.y - self.owner.y) * 1.5)

        if protected_target is None:
            self.protect_enemy_id = -1
            self.protect_target = None
        if owner_threat is not None and math.hypot(owner_threat.x - self.owner.x, (owner_threat.y - self.owner.y) * 1.5) <= guard_radius:
            protected_target = owner_threat
        elif dave is not None and dave_threat is not None and math.hypot(dave_threat.x - dave.x, (dave_threat.y - dave.y) * 1.5) <= guard_radius:
            protected_target = dave_threat
        elif target is not None and math.hypot(target.x - self.x, (target.y - self.y) * 1.5) <= roam_radius:
            protected_target = target

        # Stay with a selected threat during bite cooldown instead of running
        # back to Shelly and immediately turning around again. The cooldown
        # gates damage, not navigation or guarding.
        can_pursue = protected_target is not None and distance_from_owner <= max_roam
        if can_pursue:
            pursuit_state = "protect" if self.protect_enemy_id >= 0 else "hunt"
            dx, dy = protected_target.x - self.x, protected_target.y - self.y
            nx, ny = normalized(dx, dy)
            self.facing = 1 if dx >= 0 else -1
            speed = float(self.config.get("passive_speed", 142.0))
            applied_x = 0.0
            applied_y = 0.0
            if abs(dx) > 19.0 or abs(dy) > 13.0:
                applied_x, applied_y = game.move_actor(self, nx * speed * dt, ny * speed * 0.66 * dt)
            self._record_animation_motion(applied_x, applied_y)
            self.state = pursuit_state if abs(applied_x) + abs(applied_y) > 0.015 else "guard"
            contact_x = float(self.config.get("passive_contact_x", 28.0))
            contact_depth = float(self.config.get("passive_contact_depth", 18.0))
            if abs(dx) <= contact_x and abs(dy) <= contact_depth and self.attack_cooldown <= 0.0:
                landed = protected_target.take_damage(
                    float(self.config["passive_damage"]), game, self.owner,
                    hitstun=0.18, knockback=10.0,
                )
                if landed:
                    self.attack_cooldown = float(self.config["passive_cooldown"])
                    self.pursuit_timer = 0.0
                    self.protect_enemy_id = -1
                    self.protect_target = None
                    self.bite_flash = 0.22
                    game.audio.play("chief_bite")
                    game.log_breadcrumb("chief_autonomous_hit", enemy_id=protected_target.enemy_id)
            return

        active_party = [
            player
            for player in game.players
            if player.combat_active and player.character in {"black_dave", "shelly"}
        ]
        idle_seconds = float(self.config.get("settle_idle_seconds", 0.3))
        party_idle = bool(active_party) and all(
            player.state == "idle" and player.idle_time >= idle_seconds
            for player in active_party
        )
        if (
            party_idle
            and abs(self.x - self.owner.x) <= float(self.config.get("settle_radius_x", 38.0))
            and abs(self.y - self.owner.y) <= float(self.config.get("settle_radius_depth", 20.0))
        ):
            self.state = "sit"
            return

        follow_x = self.owner.x - self.owner.facing * 28.0
        follow_y = self.owner.y + 10.0
        dx, dy = follow_x - self.x, follow_y - self.y
        nx, ny = normalized(dx, dy)
        applied_x = 0.0
        applied_y = 0.0
        if abs(dx) + abs(dy) > 8.0:
            applied_x, applied_y = game.move_actor(self, nx * 104.0 * dt, ny * 76.0 * dt)
            self.facing = 1 if dx >= 0 else -1
        self._record_animation_motion(applied_x, applied_y)
        self.state = "follow" if abs(applied_x) + abs(applied_y) > 0.015 else "idle"

    def _update_command(self, game: Any, dt: float) -> bool:
        caller = self.command_caller
        if caller is None:
            return False
        if not caller.combat_active:
            self._clear_command()
            return False

        target = self._live_roster_enemy(game, self.command_target)
        if target is None and not self.command_return_pending:
            previous_enemy_id = self.command_enemy_id
            target = self._nearest_live_roster_enemy(game, self.x, self.y)
            if target is not None:
                self.command_target = target
                self.command_enemy_id = target.enemy_id
                game.log_breadcrumb(
                    "chief_command_retargeted",
                    player=caller.slot + 1,
                    previous_enemy_id=previous_enemy_id,
                    enemy_id=target.enemy_id,
                )
        if target is not None and not self.command_return_pending:
            self.state = "command"
            dx, dy = target.x - self.x, target.y - self.y
            nx, ny = normalized(dx, dy)
            self.facing = 1 if dx >= 0 else -1
            # Contact forgiveness deliberately exceeds the default Chief/enemy
            # push-radius sum so crowd separation cannot hold him just outside
            # his own bite forever.
            contact_x = float(self.config.get("command_contact_x", 31.0))
            contact_depth = float(self.config.get("command_contact_depth", 18.0))
            if abs(dx) > contact_x or abs(dy) > contact_depth:
                speed = float(self.config.get("command_speed", 205.0))
                applied_x, applied_y = game.move_actor(self, nx * speed * dt, ny * speed * 0.72 * dt)
                self._record_animation_motion(applied_x, applied_y)
            else:
                landed = target.take_damage(
                    float(self.config.get("command_damage", 18.0)),
                    game,
                    caller,
                    hitstun=float(self.config.get("command_hitstun", 0.34)),
                    knockback=float(self.config.get("command_knockback", 22.0)),
                )
                if landed:
                    self.bite_flash = 0.22
                    self.attack_cooldown = float(self.config.get("command_cooldown", 1.2))
                    game.audio.play("chief_bite")
                    game.add_effect("text", target.x, target.y - 48, text="GOOD BITE!", color=(255, 226, 91), duration=0.55)
                    game.log_breadcrumb("chief_command_hit", player=caller.slot + 1, enemy_id=target.enemy_id)
                self.command_enemy_id = -1
                self.command_target = None
                self.command_return_pending = True
            return True

        self.command_enemy_id = -1
        self.command_target = None
        self.command_return_pending = True
        if game.player_under_attack(caller):
            self._clear_command()
            return False

        self.state = "return_to_caller"
        caller_dx = caller.x - self.x
        caller_dy = caller.y - self.y
        if (
            abs(caller_dx) <= float(self.config.get("command_pet_distance_x", 31.0))
            and abs(caller_dy) <= float(self.config.get("command_pet_distance_depth", 20.0))
        ):
            self._clear_command()
            self.pet_cooldown = 0.0
            self.start_pet(
                caller,
                game,
                seconds=float(self.config.get("command_pet_seconds", 0.9)),
                force=True,
            )
            return True

        target_x = caller.x + caller.facing * 23.0
        target_y = caller.y + 8.0
        dx, dy = target_x - self.x, target_y - self.y
        nx, ny = normalized(dx, dy)
        self.facing = 1 if dx >= 0 else -1
        speed = float(self.config.get("command_return_speed", 178.0))
        applied_x, applied_y = game.move_actor(self, nx * speed * dt, ny * speed * 0.72 * dt)
        self._record_animation_motion(applied_x, applied_y)
        return True

    def _clear_command(self) -> None:
        self.command_enemy_id = -1
        self.command_target = None
        self.command_caller = None
        self.command_return_pending = False

    def _start_maul(self, target: Any, game: Any) -> None:
        """Hold the new maul pose after Chief has safely floored a target."""

        target = self._live_roster_enemy(game, target)
        if target is None or target.state != "down":
            self._clear_maul()
            return
        self.maul_timer = max(0.0, float(self.config.get("maul_seconds", 0.48)))
        self.maul_target_id = int(getattr(target, "enemy_id", -1))
        self.maul_target = target
        if self.maul_timer <= 0.0 or self.maul_target_id < 0:
            self._clear_maul()
            return
        self.state = "maul"
        self.animation_moving = False
        game.add_effect(
            "impact",
            target.x,
            target.y - 25,
            color=(255, 211, 92),
            radius=18,
            duration=min(0.24, self.maul_timer),
        )
        game.log_breadcrumb("chief_maul_started", enemy_id=self.maul_target_id)


@dataclass(slots=True)
class KOCompanion:
    """Autonomous KO cameo with a deliberately sparse, deterministic offense."""

    owner: Player
    config: dict[str, Any]
    x: float
    y: float
    facing: int = 1
    state: str = "idle"
    state_clock: float = 0.0
    state_duration: float = 0.0
    animation_clock: float = 0.0
    locomotion_distance: float = 0.0
    animation_state: str = "idle"
    animation_moving: bool = False
    attack_cooldown: float = -1.0
    interval_index: int = 0
    attack_index: int = 0
    completed_actions: int = 0
    pending_action: str = ""
    last_action: str = ""
    attack_landed: bool = False
    target: Enemy | None = None
    target_search_clock: float = 0.0
    super_targets: tuple[Enemy, ...] = ()
    super_target_index: int = 0
    super_hits: int = 0

    def __post_init__(self) -> None:
        if self.attack_cooldown < 0.0:
            self.attack_cooldown = self._intervals()[0]

    @property
    def feet_y(self) -> float:
        return self.y

    @property
    def animation_tick(self) -> int:
        if self.state == "skate":
            return _distance_animation_tick(
                self.locomotion_distance,
                "ko",
                "skate",
                float(self.config.get("stride_distance", 112.0)),
            )
        return _animation_tick(self.animation_clock)

    def advance_animation(self, dt: float) -> None:
        if self.state != self.animation_state:
            if self.state not in {"idle", "skate"}:
                self.animation_clock = 0.0
            self.animation_state = self.state
        if self.state != "skate":
            self.animation_clock += max(0.0, dt)

    def update(self, game: Any, dt: float) -> None:
        dt = max(0.0, float(dt))
        self.animation_moving = False
        if self.state == "prepare":
            self._update_prepare(game, dt)
            return
        if self.state in {"punch_1", "punch_2", "kick"}:
            self._update_regular_attack(game, dt)
            return
        if self.state == "super":
            self._update_super(game, dt)
            return
        if self.target is not None:
            self._update_approach(game, dt)
            return

        live_opponents = game.ko_live_opponents(self)
        if live_opponents:
            self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        if self.attack_cooldown <= 0.0 and live_opponents:
            self.target_search_clock += dt
            allow_contested = self.target_search_clock >= float(
                self.config.get("selection_fallback_seconds", 1.2)
            )
            target = game.select_ko_target(self, allow_contested=allow_contested)
            if target is not None:
                self._claim_target(target, game)
                return
        self._follow_party(game, dt)

    def _intervals(self) -> tuple[float, ...]:
        values = tuple(float(value) for value in self.config.get("attack_intervals", (20.0, 25.0, 30.0)))
        return values or (20.0, 25.0, 30.0)

    def _claim_target(self, target: Enemy, game: Any) -> None:
        target.ko_claimed = True
        # Once the warm-up begins, lingering teammate damage must not steal
        # the exact opponent KO visibly selected.
        target.burn_time = 0.0
        target.burn_tick = 0.0
        self.target = target
        every = max(1, int(self.config.get("super_every_actions", 4)))
        if (self.completed_actions + 1) % every == 0:
            self.pending_action = "super"
        else:
            cycle = tuple(str(value) for value in self.config.get("attack_cycle", ("punch_1", "punch_2", "kick")))
            self.pending_action = cycle[self.attack_index % len(cycle)]
        self.target_search_clock = 0.0
        self.facing = 1 if target.x >= self.x else -1
        self._set_state("prepare", float(self.config.get("warmup_seconds", 1.15)))
        game.log_breadcrumb(
            "ko_companion_selected_target",
            enemy=target.kind,
            enemy_id=target.enemy_id,
            action=self.pending_action,
        )

    def _claimed_target(self, game: Any) -> Enemy | None:
        target = self.target
        if target is None or not target.alive:
            return None
        if target.state in {"spawn", "ko_dazed", "ko_fall", *COUCH_RETREAT_STATES}:
            return None
        return next((enemy for enemy in getattr(game, "enemies", ()) if enemy is target), None)

    def _release_target(self) -> None:
        if self.target is not None:
            self.target.ko_claimed = False
        self.target = None

    def _cancel_action(self) -> None:
        self._release_target()
        for target in self.super_targets:
            target.ko_claimed = False
        self.super_targets = ()
        self.super_target_index = 0
        self.super_hits = 0
        self.pending_action = ""
        self.attack_landed = False
        self.target_search_clock = 0.0
        self._set_state("idle")

    def _update_prepare(self, game: Any, dt: float) -> None:
        target = self._claimed_target(game)
        if target is None:
            self._cancel_action()
            return
        self.facing = 1 if target.x >= self.x else -1
        self.state_clock += dt
        if self.state_clock < self.state_duration:
            return
        if self.pending_action == "super":
            self._start_super(game)
            return
        # Let the approach step prove that movement was actually applied
        # before exposing the skateboard state to the renderer.
        self._set_state("idle")

    def _update_approach(self, game: Any, dt: float) -> None:
        target = self._claimed_target(game)
        if target is None:
            self._cancel_action()
            return
        dx, dy = target.x - self.x, target.y - self.y
        self.facing = 1 if dx >= 0.0 else -1
        contact_x = float(self.config.get("contact_x", 30.0))
        contact_depth = float(self.config.get("contact_depth", 18.0))
        if abs(dx) <= contact_x and abs(dy) <= contact_depth:
            self.attack_landed = False
            self._set_state(
                self.pending_action,
                float(self.config.get("attack_seconds", 0.58)),
            )
            return
        nx, ny = normalized(dx, dy)
        speed = float(self.config.get("skate_speed", 220.0))
        applied_x, applied_y = game.move_actor(
            self,
            nx * speed * dt,
            ny * speed * 0.72 * dt,
        )
        self.animation_moving = abs(applied_x) + abs(applied_y) > 0.015
        if self.animation_moving:
            self.locomotion_distance += math.hypot(applied_x, applied_y)
            self.state = "skate"
        else:
            # The skateboard is an authored locomotion-only prop.  A blocked
            # approach must not leave it visible while KO is standing still.
            self.state = "idle"

    def _update_regular_attack(self, game: Any, dt: float) -> None:
        self.state_clock += dt
        impact_key = (
            "kick_impact_seconds" if self.state == "kick" else "attack_impact_seconds"
        )
        if not self.attack_landed and self.state_clock >= float(
            self.config.get(impact_key, 0.14 if self.state == "kick" else 0.10)
        ):
            target = self._claimed_target(game)
            if target is None:
                self._cancel_action()
                return
            self.attack_landed = target.begin_ko_sequence(
                game,
                self.owner,
                daze_seconds=float(self.config.get("daze_seconds", 2.4)),
                fall_seconds=float(self.config.get("fall_seconds", 0.62)),
                disappear_seconds=float(self.config.get("disappear_seconds", 0.22)),
            )
            if self.attack_landed:
                self._emit_attack_lightning(game, target, self.pending_action)
                self.last_action = self.pending_action
        if self.state_clock >= self.state_duration:
            if self.attack_landed:
                self._finish_action()
            else:
                self._cancel_action()

    def _start_super(self, game: Any) -> None:
        targets = tuple(game.ko_super_targets(self))
        if not targets:
            self._cancel_action()
            return
        for target in targets:
            target.ko_claimed = True
        self.super_targets = targets
        self.super_target_index = 0
        self.super_hits = 0
        self.attack_landed = False
        self._set_state("super", float(self.config.get("super_duration", 0.72)))
        game.audio.play("super")
        game.add_effect(
            "text",
            self.x,
            self.y - 76.0,
            text="SPEED BLITZ!",
            color=(255, 239, 118),
            duration=0.72,
        )
        game.log_breadcrumb("ko_companion_super_started", targets=len(targets))

    def _update_super(self, game: Any, dt: float) -> None:
        self.state_clock += dt
        step = float(self.config.get("super_step_seconds", 0.055))
        contact = float(self.config.get("super_contact_offset", 24.0))
        while (
            self.super_target_index < len(self.super_targets)
            and self.state_clock + 1e-9 >= (self.super_target_index + 1) * step
        ):
            target = self.super_targets[self.super_target_index]
            self.super_target_index += 1
            if not target.alive or not any(enemy is target for enemy in getattr(game, "enemies", ())):
                target.ko_claimed = False
                continue
            origin_x, origin_y = self.x, self.y
            self.facing = 1 if target.x >= origin_x else -1
            self.x = target.x - self.facing * contact
            self.y = target.y
            travel_direction = 1.0 if self.x >= origin_x else -1.0
            game.add_effect(
                "streak",
                (origin_x + self.x) * 0.5,
                (origin_y + self.y) * 0.5 - 34.0,
                color=(255, 236, 104),
                radius=max(12.0, abs(self.x - origin_x) * 0.22),
                duration=0.18,
                vx=travel_direction * 150.0,
                direction=travel_direction,
            )
            landed = target.begin_ko_sequence(
                game,
                self.owner,
                daze_seconds=float(self.config.get("daze_seconds", 2.4)),
                fall_seconds=float(self.config.get("fall_seconds", 0.62)),
                disappear_seconds=float(self.config.get("disappear_seconds", 0.22)),
            )
            if landed:
                midpoint_x = (origin_x + self.x) * 0.5
                midpoint_y = (origin_y + self.y) * 0.5 - 38.0
                effect_kind, color, base_radius, duration = KO_LIGHTNING_STYLES["super"]
                game.add_effect(
                    effect_kind,
                    midpoint_x,
                    midpoint_y,
                    color=color,
                    radius=max(base_radius, min(150.0, abs(self.x - origin_x) * 0.62)),
                    duration=duration,
                    direction=float(self.facing),
                )
                self.super_hits += 1
                self.attack_landed = True
        if self.state_clock >= self.state_duration:
            for target in self.super_targets[self.super_target_index :]:
                target.ko_claimed = False
            if self.attack_landed:
                self.last_action = "super"
                self._finish_action()
            else:
                self._cancel_action()

    def _emit_attack_lightning(
        self,
        game: Any,
        target: Enemy,
        action: str,
    ) -> None:
        """Attach one distinct crisp lightning signature to each KO strike."""

        style = KO_LIGHTNING_STYLES.get(action)
        if style is None:
            return
        effect_kind, color, radius, duration = style
        game.add_effect(
            effect_kind,
            (self.x + target.x) * 0.5,
            (self.y + target.y) * 0.5 - (26.0 if action == "kick" else 39.0),
            color=color,
            radius=radius,
            duration=duration,
            direction=float(self.facing),
        )

    def _finish_action(self) -> None:
        completed = self.pending_action
        self._release_target()
        for target in self.super_targets:
            target.ko_claimed = False
        self.super_targets = ()
        self.super_target_index = 0
        self.completed_actions += 1
        if completed in {"punch_1", "punch_2", "kick"}:
            cycle = tuple(str(value) for value in self.config.get("attack_cycle", ("punch_1", "punch_2", "kick")))
            self.attack_index = (self.attack_index + 1) % len(cycle)
        intervals = self._intervals()
        self.interval_index = (self.interval_index + 1) % len(intervals)
        self.attack_cooldown = intervals[self.interval_index]
        self.pending_action = ""
        self.target_search_clock = 0.0
        self.attack_landed = False
        # The authored attack clip contains its own follow-through.  Return to
        # idle instead of requesting an un-authored recovery sprite state.
        self._set_state("idle")

    def _follow_party(self, game: Any, dt: float) -> None:
        anchor = self.owner if self.owner.combat_active else game.nearest_player(self.x, self.y)
        if anchor is None:
            self.state = "idle"
            return
        follow_distance = float(self.config.get("follow_distance", 68.0))
        follow_depth = float(self.config.get("follow_depth_offset", 23.0))
        target_x = anchor.x - anchor.facing * follow_distance
        target_y = anchor.y + follow_depth
        dx, dy = target_x - self.x, target_y - self.y
        recall_distance = float(self.config.get("offscreen_recall_distance", 480.0))
        if math.hypot(dx, dy * 1.5) > recall_distance:
            self.x = target_x
            self.y = target_y
            self.facing = anchor.facing
            self.state = "idle"
            return
        if abs(dx) + abs(dy) <= 9.0:
            self.state = "idle"
            return
        nx, ny = normalized(dx, dy)
        speed = float(self.config.get("follow_speed", 185.0))
        applied_x, applied_y = game.move_actor(
            self,
            nx * speed * dt,
            ny * speed * 0.72 * dt,
        )
        self.animation_moving = abs(applied_x) + abs(applied_y) > 0.015
        if self.animation_moving:
            self.facing = 1 if applied_x >= 0.0 else -1
            self.locomotion_distance += math.hypot(applied_x, applied_y)
            self.state = "skate"
        else:
            self.state = "idle"

    def _set_state(self, state: str, duration: float = 0.0) -> None:
        self.state = state
        self.state_clock = 0.0
        self.state_duration = max(0.0, float(duration))


@dataclass(slots=True)
class Projectile:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    damage: float
    owner_team: str
    kind: str = "pipe"
    ttl: float = 3.0
    owner_player: Player | None = None
    owner_id: int = -1
    attack_instance_id: int = 0
    lane_tolerance: float = 0.0
    hitstun: float = 0.0
    knockback: float = 0.0
    spent: bool = False

    @property
    def feet_y(self) -> float:
        return self.y

    def update(self, game: Any, dt: float) -> None:
        if self.spent:
            return
        travel_dt = min(max(0.0, dt), max(0.0, self.ttl))
        self.ttl -= dt
        if self.kind == "bb":
            old_x = self.x
            self.x += self.vx * travel_dt
            self.y += self.vy * travel_dt
            if game.bb_projectile_hit(self, old_x, self.x):
                self.spent = True
            if self.ttl <= 0.0:
                self.spent = True
            return
        if self.kind == "taser":
            old_x = self.x
            old_y = self.y
            old_z = self.z
            self.x += self.vx * travel_dt
            self.y += self.vy * travel_dt
            self.z += self.vz * travel_dt
            projectile_hit = getattr(game, "enemy_projectile_hit", None)
            if callable(projectile_hit) and projectile_hit(self, old_x, old_y, old_z):
                self.spent = True
            if self.ttl <= 0.0:
                self.spent = True
            return
        old_x = self.x
        old_y = self.y
        old_z = self.z
        self.x += self.vx * travel_dt
        self.y += self.vy * travel_dt
        self.vz -= 420.0 * travel_dt
        self.z += self.vz * travel_dt
        glass_bottle_landed = False
        if self.z <= 0.0:
            self.z = 0.0
            if self.kind == "glass_bottle":
                glass_bottle_landed = True
            else:
                self.vz *= -0.26
                self.vx *= 0.72
                if abs(self.vz) < 28.0:
                    self.spent = True
        if self.owner_team == "enemy":
            projectile_hit = getattr(game, "enemy_projectile_hit", None)
            if callable(projectile_hit) and projectile_hit(
                self,
                old_x,
                old_y,
                old_z,
            ):
                self.spent = True
        if glass_bottle_landed:
            landed = getattr(game, "enemy_projectile_landed", None)
            if callable(landed):
                landed(self)
            self.spent = True
            return
        if self.ttl <= 0.0:
            self.spent = True


@dataclass(slots=True)
class AmmoPickup:
    """A non-solid BB tin that only a Dave player can collect."""

    x: float
    y: float
    amount: int
    ttl: float = 18.0
    kind: str = "bb_ammo"
    age: float = 0.0
    spent: bool = False

    @property
    def feet_y(self) -> float:
        return self.y

    def update(self, game: Any, dt: float) -> None:
        if self.spent:
            return
        self.age += dt
        self.ttl -= dt
        if self.ttl <= 0.0:
            self.spent = True
            return
        game.collect_bb_ammo(self)


@dataclass(slots=True)
class SuperButanePickup:
    """A non-solid propane refill that only Shelly can collect."""

    x: float
    y: float
    amount: float
    ttl: float = 18.0
    kind: str = "super_butane"
    age: float = 0.0
    spent: bool = False

    @property
    def feet_y(self) -> float:
        return self.y

    def update(self, game: Any, dt: float) -> None:
        if self.spent:
            return
        self.age += dt
        self.ttl -= dt
        if self.ttl <= 0.0:
            self.spent = True
            return
        game.collect_super_butane(self)


@dataclass(slots=True)
class Effect:
    kind: str
    x: float
    y: float
    duration: float = 0.35
    color: tuple[int, int, int] = (255, 255, 255)
    radius: float = 8.0
    text: str = ""
    age: float = 0.0
    world_space: bool = True
    projected: bool = False
    elevation: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    gravity: float = 0.0
    drag: float = 0.0
    rotation: float = 0.0
    angular_velocity: float = 0.0
    scale_start: float = 1.0
    scale_end: float = 1.0
    alpha_start: int = 255
    alpha_end: int = 0
    layer: int = 0
    direction: float = 1.0
    start_paused: bool = False

    @property
    def alive(self) -> bool:
        return self.age < self.duration

    def update(self, dt: float) -> None:
        if self.start_paused:
            self.start_paused = False
            return
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt
        if self.drag > 0.0:
            damping = max(0.0, 1.0 - self.drag * dt)
            self.vx *= damping
            self.vy *= damping
        self.rotation += self.angular_velocity * dt
        if self.kind == "text":
            self.y -= 15.0 * dt

    @property
    def progress(self) -> float:
        return clamp(self.age / max(0.001, self.duration), 0.0, 1.0)

    @property
    def visual_scale(self) -> float:
        return self.scale_start + (self.scale_end - self.scale_start) * self.progress

    @property
    def visual_alpha(self) -> int:
        return max(0, min(255, round(self.alpha_start + (self.alpha_end - self.alpha_start) * self.progress)))
