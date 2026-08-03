"""Hardware-free tests for the frame-based input manager."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from src.input_manager import (
    ACTION_BACK,
    ACTION_BB_GUN,
    ACTION_CHIEF,
    ACTION_ALT_LIGHT,
    ACTION_CONFIRM,
    ACTION_DODGE,
    ACTION_HEAVY,
    ACTION_INTERACT,
    ACTION_JOIN,
    ACTION_JUMP,
    ACTION_LIGHT,
    ACTION_PAUSE,
    ACTION_SUPER,
    ACTION_LABELS,
    InputManager,
    InputSnapshot,
    control_mapping_metadata,
)


def event(event_type: int, **attributes: object) -> pygame.event.Event:
    """Build a pygame event without posting it to a hardware event queue."""
    return pygame.event.Event(event_type, attributes)


class InputSnapshotTests(unittest.TestCase):
    """Validate immutable snapshot behavior."""

    def test_snapshot_clamps_axes_and_freezes_action_sets(self) -> None:
        held = {ACTION_LIGHT}
        snapshot = InputSnapshot(2.0, -3.0, held, {ACTION_JUMP})
        held.add(ACTION_HEAVY)

        self.assertEqual((snapshot.move_x, snapshot.move_y), (1.0, -1.0))
        self.assertEqual(snapshot.held, frozenset((ACTION_LIGHT,)))
        self.assertTrue(snapshot.was_pressed(ACTION_JUMP))
        self.assertFalse(snapshot.is_held(ACTION_HEAVY))


class InputManagerTests(unittest.TestCase):
    """Exercise keyboard, controller, hot-plug, and source-selection paths."""

    def setUp(self) -> None:
        self.manager = InputManager(discover_controllers=False)

    def tearDown(self) -> None:
        self.manager.close()

    def test_keyboard_aliases_movement_and_consumed_pressed_edges(self) -> None:
        self.manager.process_events(
            (
                event(pygame.KEYDOWN, key=pygame.K_w),
                event(pygame.KEYDOWN, key=pygame.K_RIGHT),
                event(pygame.KEYDOWN, key=pygame.K_j),
                event(pygame.KEYDOWN, key=pygame.K_RETURN),
            )
        )
        snapshot = self.manager.snapshot({"type": "keyboard"})

        self.assertEqual((snapshot.move_x, snapshot.move_y), (1.0, -1.0))
        self.assertTrue(
            {ACTION_LIGHT, ACTION_JOIN, ACTION_PAUSE, ACTION_CONFIRM}
            <= snapshot.held
        )
        self.assertEqual(snapshot.held, snapshot.pressed)

        self.manager.consume_pressed()
        self.manager.process_events(())
        next_frame = self.manager.get_snapshot({"type": "keyboard"})
        self.assertEqual(next_frame.held, snapshot.held)
        self.assertEqual(next_frame.pressed, frozenset())

        self.manager.process_events(
            (
                event(pygame.KEYUP, key=pygame.K_w),
                event(pygame.KEYUP, key=pygame.K_RIGHT),
                event(pygame.KEYUP, key=pygame.K_j),
                event(pygame.KEYUP, key=pygame.K_RETURN),
            )
        )
        released = self.manager.snapshot({"type": "keyboard"})
        self.assertEqual((released.move_x, released.move_y), (0.0, 0.0))
        self.assertEqual(released.held, frozenset())

    def test_pressed_edges_latch_until_a_simulation_step_then_do_not_repeat(self) -> None:
        keyboard = {"type": "keyboard"}
        controller = {"type": "controller", "instance_id": 64}
        self.manager.process_events(
            (
                event(pygame.KEYDOWN, key=pygame.K_x),
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=64,
                    button=pygame.CONTROLLER_BUTTON_A,
                ),
            )
        )

        # A render frame without a fixed update must not lose a quick press.
        self.manager.process_events(())
        self.assertTrue(self.manager.snapshot(keyboard).was_pressed(ACTION_LIGHT))
        self.assertTrue(self.manager.snapshot(controller).was_pressed(ACTION_JUMP))

        # Simulate the first fixed update, then the second catch-up update.
        self.manager.consume_pressed()
        keyboard_catchup = self.manager.snapshot(keyboard)
        controller_catchup = self.manager.snapshot(controller)
        self.assertFalse(keyboard_catchup.was_pressed(ACTION_LIGHT))
        self.assertFalse(controller_catchup.was_pressed(ACTION_JUMP))
        self.assertTrue(keyboard_catchup.is_held(ACTION_LIGHT))
        self.assertTrue(controller_catchup.is_held(ACTION_JUMP))

    def test_primary_keyboard_combat_layout(self) -> None:
        cases = (
            (pygame.K_x, {ACTION_LIGHT}, {ACTION_HEAVY}),
            (pygame.K_c, {ACTION_HEAVY}, {ACTION_JUMP}),
            (pygame.K_SPACE, {ACTION_JUMP, ACTION_CONFIRM}, set()),
            (pygame.K_LSHIFT, {ACTION_DODGE}, set()),
            (pygame.K_q, {ACTION_SUPER}, set()),
            (pygame.K_r, {ACTION_CHIEF}, {ACTION_SUPER}),
            (pygame.K_g, {ACTION_BB_GUN}, {ACTION_CHIEF}),
            (pygame.K_e, {ACTION_INTERACT}, set()),
        )
        for key, expected, forbidden in cases:
            with self.subTest(key=pygame.key.name(key)):
                self.manager.clear_held_state()
                self.manager.process_events((event(pygame.KEYDOWN, key=key),))
                snapshot = self.manager.snapshot({"type": "keyboard"})
                self.assertTrue(expected <= snapshot.held)
                self.assertTrue(expected <= snapshot.pressed)
                self.assertTrue(forbidden.isdisjoint(snapshot.held))

        self.manager.clear_held_state()
        self.manager.process_events((event(pygame.KEYDOWN, key=pygame.K_ESCAPE),))
        self.assertEqual(
            self.manager.snapshot({"type": "keyboard"}).held, frozenset()
        )

    def test_non_conflicting_keyboard_compatibility_aliases(self) -> None:
        expected = {
            pygame.K_j: ACTION_LIGHT,
            pygame.K_z: ACTION_ALT_LIGHT,
            pygame.K_k: ACTION_HEAVY,
            pygame.K_l: ACTION_DODGE,
            pygame.K_v: ACTION_DODGE,
            pygame.K_i: ACTION_SUPER,
            pygame.K_f: ACTION_SUPER,
        }
        for key, action in expected.items():
            with self.subTest(key=pygame.key.name(key), action=action):
                self.manager.clear_held_state()
                self.manager.process_events((event(pygame.KEYDOWN, key=key),))
                snapshot = self.manager.snapshot({"type": "keyboard"})
                self.assertTrue(snapshot.is_held(action))
                self.assertTrue(snapshot.was_pressed(action))

    def test_synthetic_mapped_controller_buttons_axes_and_metadata(self) -> None:
        instance_id = 41
        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=pygame.CONTROLLER_AXIS_LEFTX,
                    value=24_576,
                ),
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=pygame.CONTROLLER_AXIS_LEFTY,
                    value=-16_384,
                ),
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_X,
                ),
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_A,
                ),
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_RIGHTSHOULDER,
                ),
            )
        )
        snapshot = self.manager.snapshot(
            {"type": "controller", "instance_id": instance_id}
        )

        self.assertGreater(snapshot.move_x, 0.5)
        self.assertLess(snapshot.move_y, -0.25)
        self.assertTrue(
            {ACTION_LIGHT, ACTION_JUMP, ACTION_CONFIRM, ACTION_JOIN, ACTION_SUPER}
            <= snapshot.held
        )
        self.assertEqual(snapshot.held, snapshot.pressed)
        self.assertEqual(self.manager.controller_count, 1)
        metadata = self.manager.connected_controllers[0]
        self.assertEqual(metadata["instance_id"], instance_id)
        self.assertTrue(metadata["mapped"])
        self.assertTrue(metadata["synthetic"])

    def test_right_trigger_is_a_latched_chief_command_with_r3_fallback(self) -> None:
        instance_id = 42
        binding = {"type": "controller", "instance_id": instance_id}
        self.manager.add_synthetic_controller(instance_id)
        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
                    value=24_576,
                ),
            )
        )
        snapshot = self.manager.snapshot(binding)
        self.assertTrue(snapshot.is_held(ACTION_CHIEF))
        self.assertTrue(snapshot.was_pressed(ACTION_CHIEF))

        self.manager.consume_pressed()
        self.assertFalse(self.manager.snapshot(binding).was_pressed(ACTION_CHIEF))
        self.assertTrue(self.manager.snapshot(binding).is_held(ACTION_CHIEF))

        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
                    value=-32_768,
                ),
            )
        )
        self.assertFalse(self.manager.snapshot(binding).is_held(ACTION_CHIEF))

        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_RIGHTSTICK,
                ),
            )
        )
        self.assertTrue(self.manager.snapshot(binding).was_pressed(ACTION_CHIEF))

    def test_triggers_use_independent_hysteresis_and_left_stick_fallback(self) -> None:
        instance_id = 43
        binding = {"type": "controller", "instance_id": instance_id}
        self.manager.add_synthetic_controller(instance_id)
        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=pygame.CONTROLLER_AXIS_TRIGGERLEFT,
                    value=24_576,
                ),
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
                    value=24_576,
                ),
            )
        )
        snapshot = self.manager.snapshot(binding)
        self.assertTrue({ACTION_BB_GUN, ACTION_CHIEF} <= snapshot.held)
        self.assertTrue({ACTION_BB_GUN, ACTION_CHIEF} <= snapshot.pressed)

        self.manager.consume_pressed()
        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=pygame.CONTROLLER_AXIS_TRIGGERLEFT,
                    value=11_469,  # ~0.35: held inside the hysteresis band.
                ),
            )
        )
        snapshot = self.manager.snapshot(binding)
        self.assertTrue(snapshot.is_held(ACTION_BB_GUN))
        self.assertTrue(snapshot.is_held(ACTION_CHIEF))
        self.assertFalse(snapshot.was_pressed(ACTION_BB_GUN))

        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=pygame.CONTROLLER_AXIS_TRIGGERLEFT,
                    value=0,
                ),
            )
        )
        snapshot = self.manager.snapshot(binding)
        self.assertFalse(snapshot.is_held(ACTION_BB_GUN))
        self.assertTrue(snapshot.is_held(ACTION_CHIEF))

        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_LEFTSTICK,
                ),
            )
        )
        self.assertTrue(self.manager.snapshot(binding).was_pressed(ACTION_BB_GUN))

    def test_controller_layout_and_dpad_button_movement(self) -> None:
        instance_id = 7
        self.manager.add_synthetic_controller(instance_id)
        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_DPAD_LEFT,
                ),
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_DPAD_DOWN,
                ),
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_Y,
                ),
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_B,
                ),
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_LEFTSHOULDER,
                ),
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_START,
                ),
            )
        )
        snapshot = self.manager.snapshot(
            {"type": "controller", "instance_id": instance_id}
        )

        self.assertEqual((snapshot.move_x, snapshot.move_y), (-1.0, 1.0))
        self.assertTrue(
            {
                ACTION_HEAVY,
                ACTION_DODGE,
                ACTION_BACK,
                ACTION_INTERACT,
                ACTION_JOIN,
                ACTION_PAUSE,
            }
            <= snapshot.held
        )

    def test_generic_joystick_hat_and_float_axes_work_without_hardware(self) -> None:
        instance_id = 23
        self.manager.add_synthetic_controller(instance_id, mapped=False)
        self.manager.process_events(
            (
                event(
                    pygame.JOYAXISMOTION,
                    instance_id=instance_id,
                    axis=pygame.CONTROLLER_AXIS_LEFTX,
                    value=0.8,
                ),
                event(
                    pygame.JOYHATMOTION,
                    instance_id=instance_id,
                    hat=0,
                    value=(0, 1),
                ),
            )
        )
        snapshot = self.manager.snapshot(
            {"type": "controller", "instance_id": instance_id}
        )
        self.assertGreater(snapshot.move_x, 0.7)
        self.assertEqual(snapshot.move_y, -1.0)

    def test_deadzone_neutralizes_small_stick_drift(self) -> None:
        instance_id = 9
        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=0,
                    value=0.1,
                ),
                event(
                    pygame.CONTROLLERAXISMOTION,
                    instance_id=instance_id,
                    axis=1,
                    value=-0.1,
                ),
            )
        )
        snapshot = self.manager.snapshot(
            {"type": "controller", "instance_id": instance_id}
        )
        self.assertEqual((snapshot.move_x, snapshot.move_y), (0.0, 0.0))

    def test_disconnect_drops_metadata_and_returns_neutral_snapshot(self) -> None:
        instance_id = 88
        binding = {"type": "controller", "instance_id": instance_id}
        self.manager.add_synthetic_controller(instance_id)
        self.manager.process_events(
            (
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=instance_id,
                    button=pygame.CONTROLLER_BUTTON_X,
                ),
            )
        )
        self.assertTrue(self.manager.snapshot(binding).is_held(ACTION_LIGHT))

        self.manager.process_events(
            (event(pygame.CONTROLLERDEVICEREMOVED, instance_id=instance_id),)
        )
        self.assertEqual(self.manager.controller_count, 0)
        self.assertEqual(self.manager.snapshot(binding), InputSnapshot())

    def test_source_from_event_only_accepts_join_or_confirm_inputs(self) -> None:
        self.assertEqual(
            self.manager.source_from_event(
                event(pygame.KEYDOWN, key=pygame.K_SPACE)
            ),
            {"type": "keyboard"},
        )
        self.assertEqual(
            self.manager.source_from_event(
                event(pygame.KEYDOWN, key=pygame.K_RETURN)
            ),
            {"type": "keyboard"},
        )
        self.assertEqual(
            self.manager.source_from_event(
                event(
                    pygame.CONTROLLERBUTTONDOWN,
                    instance_id=55,
                    button=pygame.CONTROLLER_BUTTON_A,
                )
            ),
            {"type": "controller", "instance_id": 55},
        )
        self.assertEqual(
            self.manager.source_from_event(
                event(
                    pygame.JOYBUTTONDOWN,
                    instance_id=56,
                    button=pygame.CONTROLLER_BUTTON_START,
                )
            ),
            {"type": "controller", "instance_id": 56},
        )
        self.assertIsNone(
            self.manager.source_from_event(event(pygame.KEYDOWN, key=pygame.K_j))
        )

    def test_control_metadata_describes_primary_and_alias_layouts(self) -> None:
        metadata = control_mapping_metadata()
        keyboard = {row["action"]: row for row in metadata["keyboard"]}
        controller = {row["action"]: row for row in metadata["controller"]}

        self.assertEqual(ACTION_LABELS[ACTION_LIGHT], "Light Attack")
        self.assertEqual(keyboard[ACTION_LIGHT]["primary"], "X")
        self.assertEqual(keyboard[ACTION_LIGHT]["aliases"], ("J",))
        self.assertEqual(keyboard[ACTION_ALT_LIGHT]["primary"], "Z")
        self.assertEqual(keyboard[ACTION_HEAVY]["primary"], "C")
        self.assertEqual(keyboard[ACTION_DODGE]["primary"], "Left Shift")
        self.assertEqual(keyboard[ACTION_CHIEF]["primary"], "R")
        self.assertEqual(keyboard[ACTION_BB_GUN]["primary"], "G")
        self.assertEqual(keyboard[ACTION_PAUSE]["handled_by"], "game_menu")
        self.assertEqual(controller[ACTION_LIGHT]["primary"], "X")
        self.assertEqual(controller[ACTION_SUPER]["primary"], "RB")
        self.assertEqual(controller[ACTION_CHIEF]["primary"], "RT")
        self.assertEqual(controller[ACTION_CHIEF]["aliases"], ("R3",))
        self.assertEqual(controller[ACTION_BB_GUN]["primary"], "LT")
        self.assertEqual(controller[ACTION_BB_GUN]["aliases"], ("L3",))
        self.assertEqual(controller[ACTION_PAUSE]["primary"], "Menu / Start")

        keyboard[ACTION_LIGHT]["primary"] = "changed locally"
        fresh_keyboard = {
            row["action"]: row for row in control_mapping_metadata()["keyboard"]
        }
        self.assertEqual(fresh_keyboard[ACTION_LIGHT]["primary"], "X")

    def test_snapshot_batch_supports_four_players_and_rejects_a_fifth(self) -> None:
        bindings = [{"type": "keyboard"}]
        for instance_id in range(3):
            self.manager.add_synthetic_controller(instance_id)
            bindings.append({"type": "controller", "instance_id": instance_id})
        self.assertEqual(len(self.manager.snapshots(bindings)), 4)

        with self.assertRaisesRegex(ValueError, "maximum is 4"):
            self.manager.snapshots(
                bindings + [{"type": "controller", "instance_id": 99}]
            )

    def test_invalid_bindings_and_closed_manager_fail_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "binding type"):
            self.manager.snapshot({"type": "mouse"})
        with self.assertRaisesRegex(ValueError, "requires instance_id"):
            self.manager.snapshot({"type": "controller"})

        self.manager.close()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.manager.process_events(())


if __name__ == "__main__":
    unittest.main()
