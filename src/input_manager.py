"""Fixed-step keyboard and local-controller input for The Fades of Fate.

The manager intentionally tracks state from events instead of polling devices.
That keeps menu/gameplay input consistent and lets the test suite exercise the
complete controller path without requiring physical hardware.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import hypot
from typing import Any, Iterable, Mapping, Sequence

import pygame

try:  # pygame-ce ships this module, but keeping the fallback makes packaging safe.
    from pygame._sdl2 import controller as sdl2_controller
except (ImportError, pygame.error):  # pragma: no cover - installation fallback
    sdl2_controller = None


ActionSet = frozenset[str]
InputBinding = Mapping[str, object]

KEYBOARD_BINDING: dict[str, str] = {"type": "keyboard"}

ACTION_LIGHT = "light"
ACTION_HEAVY = "heavy"
ACTION_JUMP = "jump"
ACTION_DODGE = "dodge"
ACTION_SUPER = "super"
ACTION_CHIEF = "chief"
ACTION_SECONDARY = "secondary"
# Kept as a source-compatible import for callers that previously identified
# the left-trigger / G binding as Dave's BB action.  It now contextualizes to
# Dave's BB gun or Shelly's propane flamethrower.
ACTION_BB_GUN = ACTION_SECONDARY
ACTION_INTERACT = "interact"
ACTION_JOIN = "join"
ACTION_PAUSE = "pause"
ACTION_CONFIRM = "confirm"
ACTION_BACK = "back"


KEYBOARD_ACTION_KEYS: dict[str, frozenset[int]] = {
    ACTION_LIGHT: frozenset((pygame.K_x, pygame.K_j, pygame.K_z)),
    ACTION_HEAVY: frozenset((pygame.K_c, pygame.K_k)),
    ACTION_JUMP: frozenset((pygame.K_SPACE,)),
    ACTION_DODGE: frozenset((pygame.K_LSHIFT, pygame.K_l, pygame.K_v)),
    ACTION_SUPER: frozenset((pygame.K_q, pygame.K_i, pygame.K_f)),
    ACTION_CHIEF: frozenset((pygame.K_r,)),
    ACTION_SECONDARY: frozenset((pygame.K_g,)),
    ACTION_INTERACT: frozenset((pygame.K_e,)),
    ACTION_JOIN: frozenset((pygame.K_RETURN, pygame.K_KP_ENTER)),
    ACTION_PAUSE: frozenset((pygame.K_RETURN, pygame.K_KP_ENTER)),
    ACTION_CONFIRM: frozenset(
        (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER)
    ),
}

CONTROLLER_ACTION_BUTTONS: dict[str, frozenset[int]] = {
    ACTION_LIGHT: frozenset((pygame.CONTROLLER_BUTTON_X,)),
    ACTION_HEAVY: frozenset((pygame.CONTROLLER_BUTTON_Y,)),
    ACTION_JUMP: frozenset((pygame.CONTROLLER_BUTTON_A,)),
    ACTION_CONFIRM: frozenset((pygame.CONTROLLER_BUTTON_A,)),
    ACTION_JOIN: frozenset(
        (pygame.CONTROLLER_BUTTON_A, pygame.CONTROLLER_BUTTON_START)
    ),
    ACTION_DODGE: frozenset((pygame.CONTROLLER_BUTTON_B,)),
    ACTION_BACK: frozenset((pygame.CONTROLLER_BUTTON_B,)),
    ACTION_INTERACT: frozenset((pygame.CONTROLLER_BUTTON_LEFTSHOULDER,)),
    # RT is the primary Chief command; R3 is a digital fallback for pads whose
    # trigger axes are not exposed by their SDL mapping.
    ACTION_CHIEF: frozenset((pygame.CONTROLLER_BUTTON_RIGHTSTICK,)),
    # LT is the character-contextual secondary; L3 mirrors it for unusual
    # SDL mappings. Dave fires BBs and Shelly uses Super Butane.
    ACTION_SECONDARY: frozenset((pygame.CONTROLLER_BUTTON_LEFTSTICK,)),
    ACTION_SUPER: frozenset((pygame.CONTROLLER_BUTTON_RIGHTSHOULDER,)),
    ACTION_PAUSE: frozenset((pygame.CONTROLLER_BUTTON_START,)),
}

# Human-readable data is kept beside the executable bindings so a future
# controls/remapping page never needs to duplicate or reverse-engineer labels.
ACTION_LABELS: dict[str, str] = {
    "move": "Move",
    ACTION_LIGHT: "Light Attack",
    ACTION_HEAVY: "Heavy Attack",
    ACTION_JUMP: "Jump / Confirm",
    ACTION_DODGE: "Dodge / Back",
    ACTION_SUPER: "Super",
    ACTION_CHIEF: "Call Chief",
    ACTION_SECONDARY: "Secondary (Dave BB / Shelly Flame)",
    ACTION_INTERACT: "Interact / Revive",
    ACTION_PAUSE: "Pause / Menu",
}

_CONTROL_MAPPING_METADATA: dict[str, tuple[dict[str, object], ...]] = {
    "keyboard": (
        {"action": "move", "label": ACTION_LABELS["move"], "primary": "WASD / Arrow Keys", "aliases": ()},
        {"action": ACTION_LIGHT, "label": ACTION_LABELS[ACTION_LIGHT], "primary": "X", "aliases": ("J", "Z")},
        {"action": ACTION_HEAVY, "label": ACTION_LABELS[ACTION_HEAVY], "primary": "C", "aliases": ("K",)},
        {"action": ACTION_JUMP, "label": ACTION_LABELS[ACTION_JUMP], "primary": "Space", "aliases": ("Enter",)},
        {"action": ACTION_DODGE, "label": ACTION_LABELS[ACTION_DODGE], "primary": "Left Shift", "aliases": ("L", "V")},
        {"action": ACTION_SUPER, "label": ACTION_LABELS[ACTION_SUPER], "primary": "Q", "aliases": ("I", "F")},
        {"action": ACTION_CHIEF, "label": ACTION_LABELS[ACTION_CHIEF], "primary": "R", "aliases": ()},
        {"action": ACTION_SECONDARY, "label": ACTION_LABELS[ACTION_SECONDARY], "primary": "G", "aliases": ()},
        {"action": ACTION_INTERACT, "label": ACTION_LABELS[ACTION_INTERACT], "primary": "E", "aliases": ()},
        {
            "action": ACTION_PAUSE,
            "label": ACTION_LABELS[ACTION_PAUSE],
            "primary": "Esc",
            "aliases": ("Enter",),
            "handled_by": "game_menu",
        },
    ),
    "controller": (
        {"action": "move", "label": ACTION_LABELS["move"], "primary": "Left Stick / D-Pad", "aliases": ()},
        {"action": ACTION_LIGHT, "label": ACTION_LABELS[ACTION_LIGHT], "primary": "X", "aliases": ()},
        {"action": ACTION_HEAVY, "label": ACTION_LABELS[ACTION_HEAVY], "primary": "Y", "aliases": ()},
        {"action": ACTION_JUMP, "label": ACTION_LABELS[ACTION_JUMP], "primary": "A", "aliases": ()},
        {"action": ACTION_DODGE, "label": ACTION_LABELS[ACTION_DODGE], "primary": "B", "aliases": ()},
        {"action": ACTION_SUPER, "label": ACTION_LABELS[ACTION_SUPER], "primary": "RB", "aliases": ()},
        {"action": ACTION_CHIEF, "label": ACTION_LABELS[ACTION_CHIEF], "primary": "RT", "aliases": ("R3",)},
        {"action": ACTION_SECONDARY, "label": ACTION_LABELS[ACTION_SECONDARY], "primary": "LT", "aliases": ("L3",)},
        {"action": ACTION_INTERACT, "label": ACTION_LABELS[ACTION_INTERACT], "primary": "LB", "aliases": ()},
        {"action": ACTION_PAUSE, "label": ACTION_LABELS[ACTION_PAUSE], "primary": "Menu / Start", "aliases": ()},
    ),
}

_KEYBOARD_LEFT = frozenset((pygame.K_a, pygame.K_LEFT))
_KEYBOARD_RIGHT = frozenset((pygame.K_d, pygame.K_RIGHT))
_KEYBOARD_UP = frozenset((pygame.K_w, pygame.K_UP))
_KEYBOARD_DOWN = frozenset((pygame.K_s, pygame.K_DOWN))

_JOY_AXIS_EVENTS = frozenset((pygame.JOYAXISMOTION,))
_JOY_BUTTON_DOWN_EVENTS = frozenset((pygame.JOYBUTTONDOWN,))
_JOY_BUTTON_UP_EVENTS = frozenset((pygame.JOYBUTTONUP,))
_JOY_HAT_EVENTS = frozenset((pygame.JOYHATMOTION,))
_DEVICE_ADDED_EVENTS = frozenset(
    event_type
    for event_type in (
        pygame.JOYDEVICEADDED,
        getattr(pygame, "CONTROLLERDEVICEADDED", None),
    )
    if event_type is not None
)
_DEVICE_REMOVED_EVENTS = frozenset(
    event_type
    for event_type in (
        pygame.JOYDEVICEREMOVED,
        getattr(pygame, "CONTROLLERDEVICEREMOVED", None),
    )
    if event_type is not None
)
_CONTROLLER_AXIS_EVENTS = frozenset(
    (getattr(pygame, "CONTROLLERAXISMOTION", -1),)
)
_CONTROLLER_BUTTON_DOWN_EVENTS = frozenset(
    (getattr(pygame, "CONTROLLERBUTTONDOWN", -1),)
)
_CONTROLLER_BUTTON_UP_EVENTS = frozenset(
    (getattr(pygame, "CONTROLLERBUTTONUP", -1),)
)


@dataclass(frozen=True, slots=True)
class InputSnapshot:
    """One input source's immutable state for the current frame.

    ``move_x`` and ``move_y`` use the range ``[-1.0, 1.0]``; positive Y is
    down, matching pygame screen coordinates. ``held`` contains actions that
    remain down, while ``pressed`` contains only new presses from this frame.
    """

    move_x: float = 0.0
    move_y: float = 0.0
    held: ActionSet = frozenset()
    pressed: ActionSet = frozenset()

    def __post_init__(self) -> None:
        """Clamp axes and defensively freeze caller-provided action sets."""
        object.__setattr__(self, "move_x", _clamp_axis(self.move_x))
        object.__setattr__(self, "move_y", _clamp_axis(self.move_y))
        object.__setattr__(self, "held", frozenset(self.held))
        object.__setattr__(self, "pressed", frozenset(self.pressed))

    def is_held(self, action: str) -> bool:
        """Return whether ``action`` is currently held."""
        return action in self.held

    def was_pressed(self, action: str) -> bool:
        """Return whether ``action`` began during this frame."""
        return action in self.pressed


@dataclass(frozen=True, slots=True)
class ControllerInfo:
    """Safe, serializable metadata for one connected controller."""

    instance_id: int
    name: str
    guid: str
    axis_count: int
    button_count: int
    hat_count: int
    mapped: bool
    synthetic: bool

    def to_dict(self) -> dict[str, object]:
        """Return a fresh dictionary suitable for UI and logging code."""
        return asdict(self)


def control_mapping_metadata() -> dict[str, tuple[dict[str, object], ...]]:
    """Return display-ready keyboard and controller mappings.

    Every call returns fresh row dictionaries so controls-page code can add
    layout details without mutating the canonical labels used elsewhere.
    """
    return {
        source: tuple(dict(row) for row in rows)
        for source, rows in _CONTROL_MAPPING_METADATA.items()
    }


class InputManager:
    """Track keyboard and hot-pluggable controller input for up to four players.

    Call :meth:`process_events` once per game frame with the events returned by
    ``pygame.event.get()``. Then request one :class:`InputSnapshot` per active
    binding. Physical controllers are discovered automatically; controller
    events carrying an ``instance_id`` also auto-register a synthetic device,
    which makes the same path directly testable without hardware.
    """

    def __init__(
        self,
        *,
        max_players: int = 4,
        deadzone: float = 0.22,
        discover_controllers: bool = True,
    ) -> None:
        """Create an input manager.

        Args:
            max_players: Maximum number of snapshots accepted by
                :meth:`snapshots`; the supported range is one through four.
            deadzone: Radial left-stick dead zone in the range ``[0.0, 0.95)``.
            discover_controllers: Open controllers already attached to the PC.
                Tests normally disable this and submit synthetic events.
        """
        if not 1 <= max_players <= 4:
            raise ValueError("max_players must be between 1 and 4")
        if not 0.0 <= deadzone < 0.95:
            raise ValueError("deadzone must be at least 0.0 and below 0.95")

        self.max_players = max_players
        self.deadzone = float(deadzone)

        self._keys_down: set[int] = set()
        self._keys_pressed: set[int] = set()
        self._buttons_down: dict[int, set[int]] = {}
        self._buttons_pressed: dict[int, set[int]] = {}
        self._axes: dict[int, dict[int, float]] = {}
        self._axis_actions_down: dict[int, set[str]] = {}
        self._axis_actions_pressed: dict[int, set[str]] = {}
        self._hats: dict[int, dict[int, tuple[int, int]]] = {}

        self._controller_info: dict[int, ControllerInfo] = {}
        self._device_handles: dict[int, tuple[Any, ...]] = {}
        self._closed = False

        if discover_controllers:
            self.refresh_controllers()

    @property
    def connected_controllers(self) -> tuple[dict[str, object], ...]:
        """Return metadata dictionaries for connected controllers, by ID."""
        return tuple(
            self._controller_info[instance_id].to_dict()
            for instance_id in sorted(self._controller_info)
        )

    @property
    def controller_count(self) -> int:
        """Return the number of currently connected controllers."""
        return len(self._controller_info)

    def controller_info(self, instance_id: int) -> ControllerInfo | None:
        """Return immutable metadata for ``instance_id``, if connected."""
        return self._controller_info.get(int(instance_id))

    def process_events(self, events: Iterable[pygame.event.Event]) -> None:
        """Process all pygame events for one frame.

        New-press state remains latched until :meth:`consume_pressed` is called
        after a simulation update. This prevents both lost taps on render-only
        frames and repeated actions during fixed-step catch-up. Held state is
        retained until a matching release, controller removal, or focus loss.
        """
        self._require_open()

        for event in events:
            event_type = event.type

            if event_type in _DEVICE_ADDED_EVENTS:
                self._handle_device_added(event)
                continue
            if event_type in _DEVICE_REMOVED_EVENTS:
                instance_id = _event_instance_id(event)
                if instance_id is not None:
                    self._remove_controller(instance_id)
                continue

            if event_type == pygame.KEYDOWN:
                key = int(event.key)
                is_repeat = bool(getattr(event, "repeat", False))
                if key not in self._keys_down and not is_repeat:
                    self._keys_pressed.add(key)
                self._keys_down.add(key)
                continue
            if event_type == pygame.KEYUP:
                self._keys_down.discard(int(event.key))
                continue

            if event_type in _JOY_AXIS_EVENTS | _CONTROLLER_AXIS_EVENTS:
                instance_id = self._prepare_controller_event(event)
                if instance_id is None or self._ignore_raw_joystick_event(
                    instance_id, event_type
                ):
                    continue
                axis = int(event.axis)
                value = _normalize_event_axis(event.value)
                self._axes[instance_id][axis] = value
                trigger_action = {
                    pygame.CONTROLLER_AXIS_TRIGGERLEFT: ACTION_SECONDARY,
                    pygame.CONTROLLER_AXIS_TRIGGERRIGHT: ACTION_CHIEF,
                }.get(axis)
                if trigger_action is not None:
                    held_actions = self._axis_actions_down[instance_id]
                    # Separate press/release thresholds prevent trigger noise
                    # from producing repeated shots or cross-cancelling Chief.
                    if trigger_action not in held_actions and value >= 0.50:
                        self._axis_actions_pressed[instance_id].add(trigger_action)
                        held_actions.add(trigger_action)
                    elif trigger_action in held_actions and value <= 0.25:
                        held_actions.discard(trigger_action)
                continue

            if event_type in _JOY_BUTTON_DOWN_EVENTS | _CONTROLLER_BUTTON_DOWN_EVENTS:
                instance_id = self._prepare_controller_event(event)
                if instance_id is None or self._ignore_raw_joystick_event(
                    instance_id, event_type
                ):
                    continue
                button = int(event.button)
                held = self._buttons_down[instance_id]
                if button not in held:
                    self._buttons_pressed.setdefault(instance_id, set()).add(button)
                held.add(button)
                continue

            if event_type in _JOY_BUTTON_UP_EVENTS | _CONTROLLER_BUTTON_UP_EVENTS:
                instance_id = self._prepare_controller_event(event)
                if instance_id is None or self._ignore_raw_joystick_event(
                    instance_id, event_type
                ):
                    continue
                self._buttons_down[instance_id].discard(int(event.button))
                continue

            if event_type in _JOY_HAT_EVENTS:
                instance_id = self._prepare_controller_event(event)
                if instance_id is None or self._ignore_raw_joystick_event(
                    instance_id, event_type
                ):
                    continue
                value = tuple(int(component) for component in event.value)
                if len(value) == 2:
                    self._hats[instance_id][int(event.hat)] = value
                continue

            if event_type == getattr(pygame, "WINDOWFOCUSLOST", -1):
                self.clear_held_state()

    def update(self, events: Iterable[pygame.event.Event]) -> None:
        """Alias for :meth:`process_events`, convenient in a game loop."""
        self.process_events(events)

    def snapshot(self, binding: InputBinding) -> InputSnapshot:
        """Return the current-frame snapshot for one binding dictionary."""
        self._require_open()
        binding_type = binding.get("type")
        if binding_type == "keyboard":
            return self._keyboard_snapshot()
        if binding_type == "controller":
            if "instance_id" not in binding:
                raise ValueError("controller binding requires instance_id")
            try:
                instance_id = int(binding["instance_id"])
            except (TypeError, ValueError) as exc:
                raise ValueError("controller instance_id must be an integer") from exc
            return self._controller_snapshot(instance_id)
        raise ValueError("binding type must be 'keyboard' or 'controller'")

    def get_snapshot(self, binding: InputBinding) -> InputSnapshot:
        """Compatibility alias for :meth:`snapshot`."""
        return self.snapshot(binding)

    def snapshots(
        self, bindings: Sequence[InputBinding]
    ) -> tuple[InputSnapshot, ...]:
        """Return snapshots for one to ``max_players`` local-player bindings."""
        if len(bindings) > self.max_players:
            raise ValueError(
                f"received {len(bindings)} bindings; maximum is {self.max_players}"
            )
        return tuple(self.snapshot(binding) for binding in bindings)

    def source_from_event(
        self, event: pygame.event.Event
    ) -> dict[str, object] | None:
        """Return a join/confirm source binding represented by ``event``.

        Keyboard Space or Enter maps to the keyboard source. Controller A and
        Start map to the event's stable SDL instance ID. Unrelated events return
        ``None``. The method is pure; callers may use it before or after
        processing the same event batch.
        """
        if event.type == pygame.KEYDOWN and int(event.key) in {
            pygame.K_SPACE,
            pygame.K_RETURN,
            pygame.K_KP_ENTER,
        }:
            return dict(KEYBOARD_BINDING)

        if event.type in _JOY_BUTTON_DOWN_EVENTS | _CONTROLLER_BUTTON_DOWN_EVENTS:
            if int(event.button) not in {
                pygame.CONTROLLER_BUTTON_A,
                pygame.CONTROLLER_BUTTON_START,
            }:
                return None
            instance_id = _event_instance_id(event)
            if instance_id is not None:
                return {"type": "controller", "instance_id": instance_id}
        return None

    def add_synthetic_controller(
        self,
        instance_id: int,
        *,
        name: str = "Synthetic Controller",
        guid: str = "synthetic",
        mapped: bool = True,
    ) -> dict[str, object]:
        """Register a hardware-free controller for automated tests and tools."""
        self._require_open()
        instance_id = int(instance_id)
        self._ensure_controller_state(instance_id)
        self._controller_info[instance_id] = ControllerInfo(
            instance_id=instance_id,
            name=str(name),
            guid=str(guid),
            axis_count=6,
            button_count=15,
            hat_count=1,
            mapped=bool(mapped),
            synthetic=True,
        )
        return self._controller_info[instance_id].to_dict()

    def refresh_controllers(self) -> None:
        """Discover and open all controllers currently reported by pygame."""
        self._require_open()
        try:
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            if sdl2_controller is not None and not sdl2_controller.get_init():
                sdl2_controller.init()
            count = pygame.joystick.get_count()
        except pygame.error:
            return

        for device_index in range(count):
            self._open_device_index(device_index)

    def clear_held_state(self) -> None:
        """Release all keys, buttons, hats, and axes to prevent stuck input."""
        self._keys_down.clear()
        self._keys_pressed.clear()
        self._buttons_pressed.clear()
        self._axis_actions_pressed.clear()
        for buttons in self._buttons_down.values():
            buttons.clear()
        for axes in self._axes.values():
            axes.clear()
        for actions in self._axis_actions_down.values():
            actions.clear()
        for hats in self._hats.values():
            hats.clear()

    def consume_pressed(self) -> None:
        """Clear one-shot press edges while retaining held movement/actions.

        The main loop calls this immediately after the first fixed simulation
        update in a render frame. Subsequent catch-up updates therefore see
        held inputs, but cannot repeat attacks, joins, jumps, or menu actions.
        """
        self._require_open()
        self._keys_pressed.clear()
        self._buttons_pressed.clear()
        self._axis_actions_pressed.clear()

    def close(self) -> None:
        """Close retained pygame controller handles and clear all state."""
        if self._closed:
            return
        for handles in tuple(self._device_handles.values()):
            for handle in handles:
                try:
                    if getattr(handle, "get_init", lambda: True)():
                        handle.quit()
                except (AttributeError, pygame.error):
                    pass
        self._device_handles.clear()
        self._controller_info.clear()
        self._buttons_down.clear()
        self._buttons_pressed.clear()
        self._axes.clear()
        self._axis_actions_down.clear()
        self._axis_actions_pressed.clear()
        self._hats.clear()
        self._keys_down.clear()
        self._keys_pressed.clear()
        self._closed = True

    def __enter__(self) -> InputManager:
        """Return this manager for context-manager use."""
        self._require_open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Close device handles when leaving a context manager."""
        self.close()

    def _keyboard_snapshot(self) -> InputSnapshot:
        move_x = float(bool(self._keys_down & _KEYBOARD_RIGHT)) - float(
            bool(self._keys_down & _KEYBOARD_LEFT)
        )
        move_y = float(bool(self._keys_down & _KEYBOARD_DOWN)) - float(
            bool(self._keys_down & _KEYBOARD_UP)
        )
        held = _actions_for_inputs(self._keys_down, KEYBOARD_ACTION_KEYS)
        pressed = _actions_for_inputs(self._keys_pressed, KEYBOARD_ACTION_KEYS)
        return InputSnapshot(move_x, move_y, held, pressed)

    def _controller_snapshot(self, instance_id: int) -> InputSnapshot:
        if instance_id not in self._controller_info:
            return InputSnapshot()

        buttons = self._buttons_down.get(instance_id, set())
        pressed_buttons = self._buttons_pressed.get(instance_id, set())
        held = _actions_for_inputs(buttons, CONTROLLER_ACTION_BUTTONS)
        pressed = _actions_for_inputs(pressed_buttons, CONTROLLER_ACTION_BUTTONS)
        held = held | frozenset(self._axis_actions_down.get(instance_id, set()))
        pressed = pressed | frozenset(self._axis_actions_pressed.get(instance_id, set()))

        axes = self._axes.get(instance_id, {})
        stick_x, stick_y = _apply_radial_deadzone(
            axes.get(pygame.CONTROLLER_AXIS_LEFTX, 0.0),
            axes.get(pygame.CONTROLLER_AXIS_LEFTY, 0.0),
            self.deadzone,
        )
        digital_x, digital_y = self._controller_digital_direction(
            instance_id, buttons
        )
        move_x = float(digital_x) if digital_x else stick_x
        move_y = float(digital_y) if digital_y else stick_y
        return InputSnapshot(move_x, move_y, held, pressed)

    def _controller_digital_direction(
        self, instance_id: int, buttons: set[int]
    ) -> tuple[int, int]:
        left = pygame.CONTROLLER_BUTTON_DPAD_LEFT in buttons
        right = pygame.CONTROLLER_BUTTON_DPAD_RIGHT in buttons
        up = pygame.CONTROLLER_BUTTON_DPAD_UP in buttons
        down = pygame.CONTROLLER_BUTTON_DPAD_DOWN in buttons

        for hat_x, hat_y in self._hats.get(instance_id, {}).values():
            left = left or hat_x < 0
            right = right or hat_x > 0
            up = up or hat_y > 0  # SDL hat Y is positive upward.
            down = down or hat_y < 0

        return int(right) - int(left), int(down) - int(up)

    def _handle_device_added(self, event: pygame.event.Event) -> None:
        device_index = getattr(event, "device_index", None)
        if device_index is not None and self._open_device_index(int(device_index)):
            return

        # A synthetic add event may supply an instance ID because there is no
        # physical device index for pygame to open.
        instance_id = _event_instance_id(event)
        if instance_id is not None:
            self.add_synthetic_controller(
                instance_id,
                name=str(getattr(event, "name", "Synthetic Controller")),
                guid=str(getattr(event, "guid", "synthetic")),
                mapped=bool(getattr(event, "mapped", True)),
            )

    def _open_device_index(self, device_index: int) -> bool:
        handles: list[Any] = []
        primary: Any | None = None
        mapped = False

        try:
            if sdl2_controller is not None and sdl2_controller.is_controller(
                device_index
            ):
                primary = sdl2_controller.Controller(device_index)
                handles.append(primary)
                mapped = True
                query_handle = primary.as_joystick()
                handles.append(query_handle)
            else:
                primary = pygame.joystick.Joystick(device_index)
                primary.init()
                handles.append(primary)
                query_handle = primary

            instance_id = _handle_instance_id(primary, query_handle)
            name = _handle_name(primary, query_handle)
            guid = _safe_call(query_handle, "get_guid", "unknown")
            info = ControllerInfo(
                instance_id=instance_id,
                name=str(name),
                guid=str(guid),
                axis_count=int(_safe_call(query_handle, "get_numaxes", 0)),
                button_count=int(_safe_call(query_handle, "get_numbuttons", 0)),
                hat_count=int(_safe_call(query_handle, "get_numhats", 0)),
                mapped=mapped,
                synthetic=False,
            )
        except (IndexError, TypeError, ValueError, pygame.error):
            for handle in reversed(handles):
                try:
                    handle.quit()
                except (AttributeError, pygame.error):
                    pass
            return False

        if instance_id in self._device_handles:
            for handle in reversed(handles):
                try:
                    handle.quit()
                except (AttributeError, pygame.error):
                    pass
        else:
            self._device_handles[instance_id] = tuple(handles)
        self._controller_info[instance_id] = info
        self._ensure_controller_state(instance_id)
        return True

    def _prepare_controller_event(self, event: pygame.event.Event) -> int | None:
        instance_id = _event_instance_id(event)
        if instance_id is None:
            return None
        mapped_event = event.type in (
            _CONTROLLER_AXIS_EVENTS
            | _CONTROLLER_BUTTON_DOWN_EVENTS
            | _CONTROLLER_BUTTON_UP_EVENTS
        )
        if instance_id not in self._controller_info:
            self.add_synthetic_controller(instance_id, mapped=mapped_event)
        elif mapped_event and self._controller_info[instance_id].synthetic:
            current = self._controller_info[instance_id]
            self._controller_info[instance_id] = ControllerInfo(
                instance_id=current.instance_id,
                name=current.name,
                guid=current.guid,
                axis_count=current.axis_count,
                button_count=current.button_count,
                hat_count=current.hat_count,
                mapped=True,
                synthetic=True,
            )
        self._ensure_controller_state(instance_id)
        return instance_id

    def _ignore_raw_joystick_event(self, instance_id: int, event_type: int) -> bool:
        info = self._controller_info.get(instance_id)
        return bool(
            info is not None
            and info.mapped
            and event_type
            in (
                _JOY_AXIS_EVENTS
                | _JOY_BUTTON_DOWN_EVENTS
                | _JOY_BUTTON_UP_EVENTS
                | _JOY_HAT_EVENTS
            )
        )

    def _ensure_controller_state(self, instance_id: int) -> None:
        self._buttons_down.setdefault(instance_id, set())
        self._axes.setdefault(instance_id, {})
        self._axis_actions_down.setdefault(instance_id, set())
        self._axis_actions_pressed.setdefault(instance_id, set())
        self._hats.setdefault(instance_id, {})

    def _remove_controller(self, instance_id: int) -> None:
        for handle in self._device_handles.pop(instance_id, ()):
            try:
                if getattr(handle, "get_init", lambda: True)():
                    handle.quit()
            except (AttributeError, pygame.error):
                pass
        self._controller_info.pop(instance_id, None)
        self._buttons_down.pop(instance_id, None)
        self._buttons_pressed.pop(instance_id, None)
        self._axes.pop(instance_id, None)
        self._axis_actions_down.pop(instance_id, None)
        self._axis_actions_pressed.pop(instance_id, None)
        self._hats.pop(instance_id, None)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("InputManager is closed")


def _actions_for_inputs(
    inputs: set[int], action_map: Mapping[str, frozenset[int]]
) -> frozenset[str]:
    return frozenset(
        action for action, accepted_inputs in action_map.items() if inputs & accepted_inputs
    )


def _event_instance_id(event: pygame.event.Event) -> int | None:
    for attribute in ("instance_id", "joy", "which"):
        value = getattr(event, attribute, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def _normalize_event_axis(value: object) -> float:
    numeric = float(value)
    if numeric < -1.0:
        numeric /= 32768.0
    elif numeric > 1.0:
        numeric /= 32767.0
    return _clamp_axis(numeric)


def _clamp_axis(value: object) -> float:
    return max(-1.0, min(1.0, float(value)))


def _apply_radial_deadzone(x: float, y: float, deadzone: float) -> tuple[float, float]:
    magnitude = hypot(x, y)
    if magnitude <= deadzone or magnitude == 0.0:
        return 0.0, 0.0
    limited_magnitude = min(magnitude, 1.0)
    scaled_magnitude = (limited_magnitude - deadzone) / (1.0 - deadzone)
    scale = scaled_magnitude / magnitude
    return _clamp_axis(x * scale), _clamp_axis(y * scale)


def _safe_call(handle: Any, method_name: str, default: object) -> object:
    try:
        return getattr(handle, method_name)()
    except (AttributeError, pygame.error):
        return default


def _handle_instance_id(primary: Any, query_handle: Any) -> int:
    controller_id = getattr(primary, "id", None)
    if controller_id is not None:
        return int(controller_id)
    return int(query_handle.get_instance_id())


def _handle_name(primary: Any, query_handle: Any) -> str:
    controller_name = getattr(primary, "name", None)
    if controller_name:
        return str(controller_name)
    return str(_safe_call(query_handle, "get_name", "Unknown Controller"))
