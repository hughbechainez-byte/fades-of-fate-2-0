import copy
import unittest

from src.attack_routes import AttackRouteError, load_black_dave_v2_routes, validate_route_data
from src.config import load_gameplay
from src.crowd_control import CrowdTarget, apply_crowd_push


class AttackRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.moves = load_gameplay(validate_location_assets=False)["moves"]
        cls.library = load_black_dave_v2_routes(cls.moves)

    def test_three_semantic_routes_have_seven_progressive_steps(self) -> None:
        self.assertEqual(set(self.library.routes), {"regular", "kick", "power"})
        for action, route in self.library.routes.items():
            with self.subTest(action=action):
                self.assertEqual(len(route.steps), 7)
                self.assertEqual(len({step.step_id for step in route.steps}), 7)
                self.assertEqual(len({step.clip_id for step in route.steps}), 7)
                self.assertTrue(all(step.animation_events and step.vfx_events for step in route.steps))

    def test_resolve_and_execution_are_immutable(self) -> None:
        step = self.library.resolve("regular", 0)
        execution = self.library.capture_execution("regular", 0, metadata={"facing": 1})
        self.assertIs(execution.step, step)
        with self.assertRaises(TypeError):
            execution.metadata["facing"] = -1
        with self.assertRaises(AttackRouteError):
            self.library.resolve("regular", 7)

    def test_invalid_route_sources_fail_closed(self) -> None:
        raw = {
            "routes": {
                action: [
                    {"id": f"{action}{index}", "move_table": "light_combo", "move_index": 0,
                     "clip_id": f"{action}{index}", "startup": 0.1, "active": 0.1, "recovery": 0.1,
                     "buffer_window": 0.1, "cancel_start": 0.1, "hitbox_track": "fists", "target_cap": 1,
                     "push_profile": "light", "animation_events": ["contact"], "vfx_events": ["contact"]}
                    for index in range(7)
                ]
                for action in ("regular", "kick", "power")
            }
        }
        invalid = copy.deepcopy(raw)
        invalid["routes"]["regular"][0]["move_index"] = 999
        with self.assertRaisesRegex(AttackRouteError, "orphan move"):
            validate_route_data(invalid, self.moves)
        invalid = copy.deepcopy(raw)
        invalid["routes"]["regular"][1]["clip_id"] = "regular0"
        with self.assertRaisesRegex(AttackRouteError, "repeat"):
            validate_route_data(invalid, self.moves)
        invalid = copy.deepcopy(raw)
        known = {entry["clip_id"] for entry in raw["routes"]["regular"]}
        with self.assertRaisesRegex(AttackRouteError, "orphan clip"):
            validate_route_data(invalid, self.moves, known)


class CrowdPushTests(unittest.TestCase):
    def test_only_capped_unarmored_normal_enemies_move(self) -> None:
        pushes = apply_crowd_push(
            (
                CrowdTarget("normal", True),
                CrowdTarget("armor", True, armor=2.0),
                CrowdTarget("boss", True, boss=True),
                CrowdTarget("resistant", True, push_resistance=0.25),
                CrowdTarget("prop", False),
            ),
            distance=20.0, cap=2, armor_limit=1.0,
        )
        self.assertEqual(pushes[0].entity_id, "normal")
        self.assertEqual(pushes[0].distance, 20.0)
        self.assertEqual(pushes[1].entity_id, "resistant")
        self.assertEqual(pushes[1].distance, 15.0)

    def test_push_rejects_invalid_mechanical_limits(self) -> None:
        with self.assertRaises(ValueError):
            apply_crowd_push((), distance=0.0, cap=1)
        with self.assertRaises(ValueError):
            apply_crowd_push((), distance=1.0, cap=0)
