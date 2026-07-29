from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.chapter_content import ChapterContentError, load_chapter_content, validate_chapter_content
from src.config import ConfigError, load_gameplay, validate_gameplay
from src.location_lock import (
    LEVEL_IDS,
    MANDATORY_REFERENCE_URLS,
    REQUIRED_LANDMARK_ORDERS,
    SUPPORTED_PHYSICAL_SCENE_OBJECT_KINDS,
    LocationLockError,
    coordinate_normalized_distances,
    landmark_for_id,
    load_location_lock,
    route_for_level,
    route_for_theme,
    travel_panel_between,
    validate_location_lock,
)


ROOT = Path(__file__).resolve().parents[1]


class ChapterOneLocationLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_location_lock()
        self.gameplay = load_gameplay()
        self.content = load_chapter_content(gameplay=self.gameplay)

    def test_all_routes_load_in_locked_order_and_orientation(self) -> None:
        routes = self.manifest["routes"]
        self.assertEqual(tuple(route["level_id"] for route in routes), LEVEL_IDS)
        self.assertEqual(len({route["theme"] for route in routes}), 4)
        for route in routes:
            with self.subTest(level=route["level_id"]):
                self.assertEqual(route["travel_direction"], "northbound")
                self.assertEqual(route["screen_travel"], "left_to_right")
                self.assertEqual(route["playable_side"], "west_even")
                self.assertEqual(route["main_world_rate"], 1.0)
                self.assertIs(route_for_level(route["level_id"], self.manifest), route)
                self.assertIs(route_for_theme(route["theme"], self.manifest), route)

    def test_mandatory_live_references_keep_separate_imagery_and_access_dates(self) -> None:
        references = self.manifest["mandatory_references"]
        self.assertEqual(tuple(item["url"] for item in references), MANDATORY_REFERENCE_URLS)
        self.assertEqual(len({item["id"] for item in references}), len(references))
        for reference in references:
            self.assertEqual(reference["access_date"], "2026-07-27")
            self.assertTrue(reference["imagery_date"])
            self.assertNotEqual(reference["imagery_date"], reference["access_date"])
            self.assertTrue(reference["address"])
            self.assertTrue(reference["view_direction"])

    def test_exact_route_orders_and_coordinate_derived_distances_validate(self) -> None:
        for route in self.manifest["routes"]:
            with self.subTest(level=route["level_id"]):
                landmarks = route["landmarks"]
                self.assertEqual(
                    tuple(landmark["id"] for landmark in landmarks),
                    REQUIRED_LANDMARK_ORDERS[route["level_id"]],
                )
                expected = coordinate_normalized_distances(landmarks)
                for landmark, normalized in zip(landmarks, expected):
                    self.assertAlmostEqual(
                        landmark["normalized_route_distance"],
                        normalized,
                        delta=0.002,
                    )
                    for field in (
                        "address",
                        "latitude",
                        "longitude",
                        "source_date",
                        "imagery_date",
                        "access_date",
                        "source_urls",
                        "view_direction",
                        "durable_massing",
                        "parking_setback",
                        "driveway_placement",
                        "neighboring_anchors",
                        "confidence",
                        "setback",
                        "world_x",
                    ):
                        self.assertIn(field, landmark)

    def test_spacing_changes_over_fifteen_percent_require_a_reason(self) -> None:
        invalid = deepcopy(self.manifest)
        invalid["routes"][0]["landmarks"][1].pop("compression_reason")
        with self.assertRaisesRegex(LocationLockError, "requires compression_reason"):
            validate_location_lock(invalid, project_root=ROOT, validate_assets=False)

    def test_every_manifest_id_is_globally_unique(self) -> None:
        identifiers: list[str] = [
            item["id"] for item in self.manifest["mandatory_references"]
        ]
        for route in self.manifest["routes"]:
            identifiers.extend(item["id"] for item in route["landmarks"])
            identifiers.extend(item["id"] for item in route["opposite_side_landmarks"])
            identifiers.extend(item["id"] for item in route["registered_features"])
        for panel in self.manifest["travel_panels"]:
            identifiers.append(panel["id"])
            identifiers.extend(item["id"] for item in panel["waypoints"])
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_location_assets_have_declared_sizes_and_opaque_main_worlds(self) -> None:
        validated = validate_location_lock(
            deepcopy(self.manifest),
            project_root=ROOT,
            validate_assets=True,
        )
        self.assertEqual(validated["schema_version"], 2)

        missing = deepcopy(self.manifest)
        missing["routes"][0]["main_panorama_asset"] = (
            "assets/stage/chapter1_location_locked/does_not_exist.png"
        )
        with self.assertRaisesRegex(LocationLockError, "is missing"):
            validate_location_lock(missing, project_root=ROOT, validate_assets=True)

        transparent_main = deepcopy(self.manifest)
        transparent_main["routes"][0]["main_panorama_asset"] = (
            transparent_main["routes"][0]["near_asset"]
        )
        with self.assertRaisesRegex(LocationLockError, "fully opaque"):
            validate_location_lock(
                transparent_main,
                project_root=ROOT,
                validate_assets=True,
            )

    def test_raw_gameplay_references_manifest_ids_without_duplicating_route_facts(self) -> None:
        raw = json.loads((ROOT / "data" / "gameplay.json").read_text(encoding="utf-8-sig"))
        levels = raw["campaign"]["chapters"][0]["levels"]
        for level in levels:
            route = route_for_level(level["id"], self.manifest)
            self.assertNotIn("landmarks", level)
            self.assertNotIn("stage_width", level)
            self.assertNotIn("background_theme", level)
            self.assertEqual(
                tuple(level["landmark_ids"]),
                tuple(item["id"] for item in route["landmarks"]),
            )
            self.assertEqual(level["start"], {"id": route["start_anchor_id"]})
            self.assertEqual(level["end"], {"id": route["end_anchor_id"]})

    def test_gameplay_hydrates_manifest_landmarks_and_rejects_drift(self) -> None:
        levels = self.gameplay["campaign"]["chapters"][0]["levels"]
        for level in levels:
            route = route_for_level(level["id"], self.manifest)
            self.assertEqual(level["stage_width"], route["world_width"])
            self.assertEqual(level["background_theme"], route["theme"])
            self.assertEqual(
                [(item["id"], item["x"]) for item in level["landmarks"]],
                [(item["id"], item["world_x"]) for item in route["landmarks"]],
            )
            features = {item["id"]: item for item in route["registered_features"]}
            for obstacle in level["stage_geometry"]["obstacles"]:
                feature = features[obstacle["location_feature_id"]]
                self.assertLessEqual(abs(obstacle["x"] - feature["world_x"]), 8)

        drifted = deepcopy(self.gameplay)
        drifted["campaign"]["chapters"][0]["levels"][0]["landmarks"][0]["x"] += 9
        with self.assertRaisesRegex(ConfigError, "landmark sprouts_parking_lot x drifted"):
            validate_gameplay(drifted)

    def test_narrative_runtime_and_manifest_endpoints_agree(self) -> None:
        runtime_levels = {
            level["id"]: level
            for level in self.gameplay["campaign"]["chapters"][0]["levels"]
        }
        for content_level in self.content["levels"]:
            level_id = content_level["runtime_level_id"]
            route = route_for_level(level_id, self.manifest)
            runtime = runtime_levels[level_id]
            narrative = content_level["route"]
            self.assertEqual(narrative["start_anchor_id"], route["start_anchor_id"])
            self.assertEqual(narrative["end_anchor_id"], route["end_anchor_id"])
            self.assertEqual(runtime["start"]["id"], route["start_anchor_id"])
            self.assertEqual(runtime["end"]["id"], route["end_anchor_id"])

        drifted = deepcopy(self.content)
        drifted["levels"][2]["route"]["end_anchor_id"] = "revive_approach"
        with self.assertRaisesRegex(ChapterContentError, "end anchor drifted"):
            validate_chapter_content(
                drifted,
                gameplay=self.gameplay,
                location_manifest=self.manifest,
            )

    def test_awaken_is_950_n_second_and_bmx_is_the_same_lot_endpoint(self) -> None:
        finale = route_for_level("chapter_1_level_4", self.manifest)
        awaken = landmark_for_id(finale, "awaken_church_lot")
        bmx = landmark_for_id(finale, "daves_bmx")
        self.assertEqual(awaken["address"], "950 N 2nd St")
        self.assertEqual(bmx["address"], "950 N 2nd St")
        self.assertEqual(finale["start_anchor_id"], "awaken_church_lot")
        self.assertEqual(finale["end_anchor_id"], "daves_bmx")
        self.assertEqual(bmx["world_x"], 1080)
        self.assertNotIn("Revive", " ".join(item["display_name"] for item in finale["landmarks"]))

    def test_noncombat_handoffs_include_both_required_moving_panels(self) -> None:
        i8_bridge = travel_panel_between(
            "chapter_1_level_2",
            "chapter_1_level_3",
            self.manifest,
        )
        self.assertEqual(i8_bridge["presentation"], "moving_panel")
        self.assertEqual(
            [item["id"] for item in i8_bridge["waypoints"]],
            ["i8_shadow_departure", "showroom_690", "fuel_smog_row_710", "soapy_joes_arrival"],
        )
        awaken_bridge = travel_panel_between(
            "chapter_1_level_3",
            "chapter_1_level_4",
            self.manifest,
        )
        self.assertEqual(awaken_bridge["presentation"], "moving_panel")
        self.assertEqual(awaken_bridge["waypoints"][-1]["address"], "950 N 2nd St")

    def test_optional_layer_profile_fields_are_always_optional(self) -> None:
        valid = deepcopy(self.manifest)
        valid["routes"][0]["projection_profile_id"] = "legacy-bridge-profile"
        valid["routes"][0]["sky_profile_id"] = "legacy-sky-profile"
        validated = validate_location_lock(
            valid,
            project_root=ROOT,
            validate_assets=False,
        )
        self.assertIs(validated["schema_version"], 2)

        invalid = deepcopy(self.manifest)
        invalid["routes"][0]["projection_profile_id"] = 7
        with self.assertRaisesRegex(LocationLockError, "must be non-empty text"):
            validate_location_lock(invalid, project_root=ROOT, validate_assets=False)

    def test_layer_asset_pairing_is_required(self) -> None:
        missing_size = deepcopy(self.manifest)
        missing_size["routes"][1].pop("far_skyline_asset_size")
        with self.assertRaisesRegex(LocationLockError, "must declare far_skyline_asset and far_skyline_asset_size together"):
            validate_location_lock(
                missing_size,
                project_root=ROOT,
                validate_assets=False,
            )

        missing_asset = deepcopy(self.manifest)
        missing_asset["routes"][1].pop("far_skyline_asset")
        with self.assertRaisesRegex(LocationLockError, "must declare far_skyline_asset and far_skyline_asset_size together"):
            validate_location_lock(
                missing_asset,
                project_root=ROOT,
                validate_assets=False,
            )

    def test_optional_layer_assets_validate_size_and_alpha(self) -> None:
        from PIL import Image

        locked_art_root = ROOT / "assets" / "stage" / "chapter1_location_locked"
        with TemporaryDirectory(dir=locked_art_root) as temp_root:
            temp_dir = Path(temp_root)
            route = deepcopy(self.manifest)["routes"][2]
            route["physical_scene_objects"] = []
            world_width = int(route["world_width"])
            route["near_asset"] = route["far_asset"]
            route["far_haze_asset"] = route["far_asset"]
            route["far_skyline_asset"] = route["far_asset"]
            route["far_skyline_asset_size"] = [world_width, 360]
            route["far_haze_asset_size"] = [world_width, 360]

            opaque = temp_dir / "not_alpha.png"
            Image.new("RGB", (world_width, 360), (10, 10, 10)).save(opaque)
            with_alpha = temp_dir / "with_alpha.png"
            Image.new("RGBA", (world_width, 360), (10, 10, 10, 128)).save(with_alpha)
            ground_valid = temp_dir / "ground_valid.png"
            valid_ground = Image.new("RGBA", (world_width, 360), (12, 12, 12, 0))
            for x in range(world_width):
                for y in range(250, 360):
                    valid_ground.putpixel((x, y), (12, 12, 12, 255))
            valid_ground.save(ground_valid)

            route["far_skyline_asset"] = str(with_alpha.relative_to(ROOT))
            route["far_skyline_asset_size"] = [world_width, 360]
            route["far_haze_asset"] = str(with_alpha.relative_to(ROOT))
            route["far_haze_asset_size"] = [world_width, 360]
            route["ground_asset"] = str(ground_valid.relative_to(ROOT))
            route["ground_asset_size"] = [world_width, 360]

            candidate = deepcopy(self.manifest)
            candidate["routes"][2] = route
            route["ground_opaque_from_y"] = 250
            validate_location_lock(candidate, project_root=ROOT, validate_assets=True)

            route["far_haze_asset"] = str(opaque.relative_to(ROOT))
            with self.assertRaisesRegex(LocationLockError, "must retain a transparent alpha channel"):
                validate_location_lock(candidate, project_root=ROOT, validate_assets=True)

    def test_ground_coverage_requires_opaque_floor_at_or_below_threshold(self) -> None:
        from PIL import Image

        locked_art_root = ROOT / "assets" / "stage" / "chapter1_location_locked"
        with TemporaryDirectory(dir=locked_art_root) as temp_root:
            temp_dir = Path(temp_root)
            route = deepcopy(self.manifest)["routes"][0]
            world_width = int(route["world_width"])
            base = Path(route["far_asset"])
            valid_ground = temp_dir / "ground_valid.png"
            invalid_ground = temp_dir / "ground_invalid.png"

            valid = Image.new("RGBA", (world_width, 360), (8, 8, 8, 0))
            for x in range(world_width):
                for y in range(160, 360):
                    valid.putpixel((x, y), (8, 8, 8, 255))
            valid.save(valid_ground)

            invalid = Image.new("RGBA", (world_width, 360), (8, 8, 8, 0))
            for x in range(world_width):
                for y in range(160, 360):
                    invalid.putpixel((x, y), (8, 8, 8, 255))
            for x in range(world_width):
                invalid.putpixel((x, 359), (8, 8, 8, 0))
            invalid.save(invalid_ground)

            route["ground_asset"] = str(valid_ground.relative_to(ROOT))
            route["ground_asset_size"] = [world_width, 360]
            route["ground_opaque_from_y"] = 160
            route["far_skyline_asset"] = str(base)
            route["far_skyline_asset_size"] = [world_width, 360]

            candidate = deepcopy(self.manifest)
            candidate["routes"][0] = route
            validate_location_lock(candidate, project_root=ROOT, validate_assets=True)

            route["ground_asset"] = str(invalid_ground.relative_to(ROOT))
            with self.assertRaisesRegex(
                LocationLockError,
                "must be fully opaque at and below",
            ):
                validate_location_lock(candidate, project_root=ROOT, validate_assets=True)

    def test_physical_scene_objects_require_well_formed_entries(self) -> None:
        invalid = deepcopy(self.manifest)
        invalid["routes"][0]["physical_scene_objects"] = (
            {"id": "bad_object", "kind": "lamp_post"},
        )
        with self.assertRaisesRegex(
            LocationLockError,
            "physical_scene_objects must be a list",
        ):
            validate_location_lock(invalid, project_root=ROOT, validate_assets=False)

        malformed = deepcopy(self.manifest)
        malformed["routes"][1]["physical_scene_objects"] = [{"id": "bad", "kind": "sedan", "world_x": "N/A", "height": -1}]
        with self.assertRaisesRegex(LocationLockError, "physical_scene_objects\\[0\\].world_x"):
            validate_location_lock(malformed, project_root=ROOT, validate_assets=False)

    def test_physical_scene_objects_share_renderer_kind_registry(self) -> None:
        self.assertEqual(
            SUPPORTED_PHYSICAL_SCENE_OBJECT_KINDS,
            frozenset({"sedan"}),
        )
        unsupported = deepcopy(self.manifest)
        unsupported["routes"][0]["physical_scene_objects"][0]["kind"] = "lamp_post"
        with self.assertRaisesRegex(LocationLockError, "kind must be renderer-supported"):
            validate_location_lock(unsupported, project_root=ROOT, validate_assets=False)

    def test_physical_scene_objects_stay_outside_walkable_rails_or_collide(self) -> None:
        intruding = deepcopy(self.manifest)
        intruding_object = intruding["routes"][0]["physical_scene_objects"][0]
        intruding_object["world_x"] = 470
        intruding_object["depth"] = 247
        with self.assertRaisesRegex(LocationLockError, "outside the walkable rail"):
            validate_location_lock(intruding, project_root=ROOT, validate_assets=False)

        collision_backed = deepcopy(intruding)
        collision_backed_object = collision_backed["routes"][0]["physical_scene_objects"][0]
        collision_backed_object["collision_obstacle_id"] = "sprouts_cart_return"
        validate_location_lock(
            collision_backed,
            project_root=ROOT,
            validate_assets=False,
        )

        dangling_collision = deepcopy(collision_backed)
        dangling_collision["routes"][0]["physical_scene_objects"][0][
            "collision_obstacle_id"
        ] = "missing_obstacle"
        with self.assertRaisesRegex(
            LocationLockError,
            "must reference a gameplay obstacle",
        ):
            validate_location_lock(
                dangling_collision,
                project_root=ROOT,
                validate_assets=False,
            )

    def test_physical_sedans_must_reach_the_visible_ground_contact_band(self) -> None:
        floating = deepcopy(self.manifest)
        route = floating["routes"][0]
        route["physical_scene_objects"][0]["depth"] = (
            route["ground_opaque_from_y"] - 1
        )
        with self.assertRaisesRegex(
            LocationLockError,
            "visible ground contact band",
        ):
            validate_location_lock(
                floating,
                project_root=ROOT,
                validate_assets=False,
            )

        elevated = deepcopy(self.manifest)
        elevated["routes"][0]["physical_scene_objects"][0]["elevation"] = 1
        with self.assertRaisesRegex(
            LocationLockError,
            "elevation must be zero",
        ):
            validate_location_lock(
                elevated,
                project_root=ROOT,
                validate_assets=False,
            )

    def test_production_mapping_never_references_old_generic_stage_art(self) -> None:
        raw = json.dumps(self.manifest).lower()
        self.assertNotIn("second_street_route_level1_panorama_v1", raw)
        self.assertNotIn("second_street_level2_i8_v1", raw)
        self.assertNotIn("second_street_level3_soapy_revive_v1", raw)
        self.assertNotIn("second_street_level4_awaken_v1", raw)
        for route in self.manifest["routes"]:
            for field in ("main_panorama_asset", "far_asset", "near_asset"):
                self.assertIn("chapter1_location_locked", route[field])


if __name__ == "__main__":
    unittest.main()
