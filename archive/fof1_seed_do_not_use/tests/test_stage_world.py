"""Contracts for the chunked world-space Chapter 1 stage topology."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_json  # noqa: E402
from src.location_lock import load_location_lock, location_routes  # noqa: E402
from src.stage_world import StageWorld, StageWorldError  # noqa: E402


class StageWorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.location_manifest = load_location_lock(
            PROJECT_ROOT / "data" / "chapter1_location_lock.json",
            project_root=PROJECT_ROOT,
        )
        cls.chunk_manifest = load_json("data/stage_chunks.json")

    def test_every_route_is_covered_by_contiguous_panel_chunks(self) -> None:
        for route in location_routes(self.location_manifest):
            with self.subTest(theme=route["theme"]):
                world = StageWorld.from_route(route, self.chunk_manifest)
                self.assertGreaterEqual(len(world.chunks), 2)
                self.assertEqual(world.chunks[0].world_x, 0)
                self.assertEqual(world.chunks[-1].world_right, route["world_width"])
                self.assertEqual(
                    sum(chunk.width for chunk in world.chunks),
                    route["world_width"],
                )
                for chunk in world.chunks:
                    self.assertEqual(
                        {piece.layer for piece in chunk.layer_pieces},
                        {"far_skyline", "architecture", "ground", "near_occluder"},
                    )
                    self.assertTrue(chunk.seam_anchor)
                    for piece in chunk.layer_pieces:
                        self.assertLessEqual(piece.width, chunk.width + 48)
                        self.assertLessEqual(piece.height, 360)

    def test_culling_keeps_nearby_chunks_and_drops_distant_sections(self) -> None:
        route = next(
            route
            for route in location_routes(self.location_manifest)
            if route["theme"] == "sprouts_el_cilantro"
        )
        world = StageWorld.from_route(route, self.chunk_manifest)
        start = world.active_chunks(0, 640, margin=0)
        end = world.active_chunks(2560, 640, margin=0)
        self.assertEqual(tuple(chunk.chunk_id for chunk in start), (
            "sprouts_el_cilantro_chunk_00",
        ))
        self.assertEqual(tuple(chunk.chunk_id for chunk in end), (
            "sprouts_el_cilantro_chunk_03",
        ))
        self.assertEqual(
            len(world.visible_layer_pieces("architecture", 0, 640, margin=0)),
            1,
        )

    def test_world_locked_and_bounded_parallax_offsets_share_one_camera(self) -> None:
        route = next(
            route
            for route in location_routes(self.location_manifest)
            if route["theme"] == "seven_eleven_underpass"
        )
        world = StageWorld.from_route(route, self.chunk_manifest)
        main_delta = world.layer_offset("architecture", 50, 640) - world.layer_offset("architecture", 0, 640)
        far_delta = world.layer_offset("far_skyline", 50, 640) - world.layer_offset("far_skyline", 0, 640)
        near_delta = world.layer_offset("near_occluder", 50, 640) - world.layer_offset("near_occluder", 0, 640)
        self.assertEqual(main_delta, -50)
        self.assertLess(abs(far_delta), abs(main_delta))
        self.assertGreater(abs(near_delta), abs(main_delta))
        self.assertLessEqual(
            abs(world.layer_offset("far_skyline", 2560, 640) - world.layer_offset("architecture", 2560, 640)),
            route["far_max_offset"],
        )

    def test_chunk_debug_snapshot_keeps_system_ownership_visible(self) -> None:
        route = next(iter(location_routes(self.location_manifest)))
        world = StageWorld.from_route(route, self.chunk_manifest)
        snapshot = world.debug_snapshot(400, 640)
        self.assertEqual(snapshot["theme"], route["theme"])
        self.assertTrue(snapshot["active_chunk_ids"])
        self.assertIn("layer_offsets", snapshot)
        self.assertIn("active_landmark_ids", snapshot)
        self.assertIn("active_collision_ids", snapshot)
        self.assertIn("active_spawn_marker_ids", snapshot)

    def test_gap_in_chunk_topology_is_rejected(self) -> None:
        route = next(iter(location_routes(self.location_manifest)))
        broken = deepcopy(self.chunk_manifest)
        broken["routes"][0]["chunks"][1]["world_x"] += 1
        with self.assertRaises(StageWorldError):
            StageWorld.from_route(route, broken)


if __name__ == "__main__":
    unittest.main()
