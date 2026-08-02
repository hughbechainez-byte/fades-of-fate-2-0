from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.config import (
    CONTENT_ROOT_ENV,
    ConfigError,
    active_campaign_level,
    active_resource_root,
    clear_resource_root_cache,
    load_gameplay,
    load_json,
    resource_path,
    validate_gameplay,
)


class GameplayConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_gameplay()

    def test_shipped_engine_configuration_is_valid(self) -> None:
        self.assertEqual(validate_gameplay(deepcopy(self.data))["engine"]["schema_version"], 2)

    def test_invalid_camera_and_physics_tuning_fail_early(self) -> None:
        invalid_camera = deepcopy(self.data)
        invalid_camera["engine"]["camera"]["dead_zone_left"] = 500
        invalid_camera["engine"]["camera"]["dead_zone_right"] = 200
        with self.assertRaisesRegex(ConfigError, "dead zone"):
            validate_gameplay(invalid_camera)

        invalid_radius = deepcopy(self.data)
        invalid_radius["engine"]["physics"]["enemy_radius_depth"] = 0
        with self.assertRaisesRegex(ConfigError, "enemy_radius_depth"):
            validate_gameplay(invalid_radius)

    def test_encounter_camera_lock_must_fit_the_stage(self) -> None:
        invalid = deepcopy(self.data)
        invalid["encounters"][0]["camera_x"] = invalid["meta"]["stage_width"]
        active_campaign_level(invalid)["encounters"][0]["camera_x"] = invalid["meta"]["stage_width"]
        with self.assertRaisesRegex(ConfigError, "camera_x"):
            validate_gameplay(invalid)

    def test_security_reinforcement_schema_and_couch_finale_guardrail_fail_fast(self) -> None:
        missing_speech = deepcopy(self.data)
        missing_speech["campaign"]["chapters"][0]["levels"][0]["encounters"][1][
            "post_clear_reinforcements"
        ][0]["speech"] = ""
        with self.assertRaisesRegex(ConfigError, "requires speech"):
            validate_gameplay(missing_speech)

        couch_security = deepcopy(self.data)
        finale = couch_security["campaign"]["chapters"][0]["levels"][-1]
        finale["encounters"][-1]["post_clear_reinforcements"] = [
            {"name": "Invalid Guard", "base": ["security"], "speech": "GET OUT!"}
        ]
        with self.assertRaisesRegex(ConfigError, "Couch final wave"):
            validate_gameplay(couch_security)

    def test_bb_ammo_and_drop_window_fail_fast_when_invalid(self) -> None:
        invalid_ammo = deepcopy(self.data)
        invalid_ammo["bb_gun"]["start_ammo"] = invalid_ammo["bb_gun"]["max_ammo"] + 1
        with self.assertRaisesRegex(ConfigError, "start_ammo"):
            validate_gameplay(invalid_ammo)

        invalid_drop = deepcopy(self.data)
        invalid_drop["bb_gun"]["drop_ko_max"] = 5
        with self.assertRaisesRegex(ConfigError, "2-4"):
            validate_gameplay(invalid_drop)

    def test_shelly_super_butane_contract_fails_fast_when_invalid(self) -> None:
        invalid_meter = deepcopy(self.data)
        invalid_meter["shelly_propane"]["activation_minimum"] = 0
        with self.assertRaisesRegex(ConfigError, "activation_minimum"):
            validate_gameplay(invalid_meter)

        invalid_drop = deepcopy(self.data)
        invalid_drop["shelly_propane"]["drop_ko_max"] = 5
        with self.assertRaisesRegex(ConfigError, "2-4"):
            validate_gameplay(invalid_drop)

        invalid_gain = deepcopy(self.data)
        invalid_gain["players"]["shelly"]["super_gain_multiplier"] = 0
        with self.assertRaisesRegex(ConfigError, "super_gain_multiplier"):
            validate_gameplay(invalid_gain)

        invalid_burst = deepcopy(self.data)
        invalid_burst["players"]["shelly"]["frenzy_burst_targets"] = 0
        with self.assertRaisesRegex(ConfigError, "frenzy_burst_targets"):
            validate_gameplay(invalid_burst)

        invalid_goal = deepcopy(self.data)
        invalid_goal["companion_ai"]["cpu_shelly_frenzy_goal"] = 1
        with self.assertRaisesRegex(ConfigError, "at least two uses"):
            validate_gameplay(invalid_goal)

    def test_bass_drop_and_crowd_scaling_tuning_fail_fast_when_invalid(self) -> None:
        invalid_super = deepcopy(self.data)
        invalid_super["players"]["black_dave"]["super_damage"] = 0
        with self.assertRaisesRegex(ConfigError, "super_damage"):
            validate_gameplay(invalid_super)

        invalid_fists = deepcopy(self.data)
        invalid_fists["players"]["black_dave"]["fist_effects"]["color"] = [999, 0, 0]
        with self.assertRaisesRegex(ConfigError, "fist_effects.color"):
            validate_gameplay(invalid_fists)

        invalid_flame_chain = deepcopy(self.data)
        invalid_flame_chain["players"]["black_dave"]["fist_flames"]["activation_presses"] = 5
        with self.assertRaisesRegex(ConfigError, "at least six"):
            validate_gameplay(invalid_flame_chain)

        invalid_density = deepcopy(self.data)
        invalid_density["scaling"]["encounter_density_multiplier"] = [1.2, 1.2]
        with self.assertRaisesRegex(ConfigError, "encounter_density_multiplier"):
            validate_gameplay(invalid_density)

        invalid_radius = deepcopy(self.data)
        invalid_radius["moves"]["light_combo"][1]["combo_radius"] = 0
        with self.assertRaisesRegex(ConfigError, "combo_radius"):
            validate_gameplay(invalid_radius)

        invalid_target_cap = deepcopy(self.data)
        invalid_target_cap["engine"]["physics"]["player_attack_max_targets"] = 2
        with self.assertRaisesRegex(ConfigError, "exactly one"):
            validate_gameplay(invalid_target_cap)

        invalid_focus_cap = deepcopy(self.data)
        invalid_focus_cap["scaling"]["focused_enemy_queue_cap"] = [1, 1, 1, 1]
        with self.assertRaisesRegex(ConfigError, "focused_enemy_queue_cap"):
            validate_gameplay(invalid_focus_cap)

    def test_player_move_contract_rejects_missing_or_invalid_numbers(self) -> None:
        positive_fields = ("startup", "active", "recovery", "range_x", "range_y")
        for field in positive_fields:
            with self.subTest(field=field):
                invalid = deepcopy(self.data)
                invalid["moves"]["light_combo"][0][field] = 0
                with self.assertRaisesRegex(
                    ConfigError, rf"moves\.light_combo\[0\]\.{field}"
                ):
                    validate_gameplay(invalid)

        payload_fields = ("damage", "hitstun", "knockback", "meter")
        for field in payload_fields:
            with self.subTest(field=field):
                invalid = deepcopy(self.data)
                invalid["moves"]["light_combo"][0][field] = -0.01
                with self.assertRaisesRegex(
                    ConfigError, rf"moves\.light_combo\[0\]\.{field}"
                ):
                    validate_gameplay(invalid)

        missing_heavy = deepcopy(self.data)
        missing_heavy["moves"].pop("heavy")
        with self.assertRaisesRegex(ConfigError, r"moves\.heavy"):
            validate_gameplay(missing_heavy)

        invalid_air_range = deepcopy(self.data)
        invalid_air_range["moves"]["air"]["range_y"] = float("nan")
        with self.assertRaisesRegex(ConfigError, r"moves\.air\.range_y"):
            validate_gameplay(invalid_air_range)

        nonnumeric_light = deepcopy(self.data)
        nonnumeric_light["moves"]["light_combo"][1]["startup"] = "fast"
        with self.assertRaisesRegex(
            ConfigError, r"moves\.light_combo\[1\]\.startup"
        ):
            validate_gameplay(nonnumeric_light)

    def test_character_light_combo_sequences_require_valid_integer_indices(self) -> None:
        valid = deepcopy(self.data)
        valid["players"]["shelly"]["light_combo_sequence"] = [0, 2, 3]
        validate_gameplay(valid)

        invalid_cases = (
            ("black_dave", [len(self.data["moves"]["light_combo"])]),
            ("shelly", []),
            ("shelly", [1.0]),
            ("shelly", [True]),
        )
        for character, sequence in invalid_cases:
            with self.subTest(character=character, sequence=sequence):
                invalid = deepcopy(self.data)
                invalid["players"][character]["light_combo_sequence"] = sequence
                with self.assertRaisesRegex(
                    ConfigError,
                    rf"players\.{character}\.light_combo_sequence",
                ):
                    validate_gameplay(invalid)

    def test_combat_physics_enemy_scoring_and_dodge_tuning_fail_fast(self) -> None:
        nonnegative_physics = (
            "player_attack_reach_bonus",
            "player_attack_aim_range_bonus",
            "player_attack_lane_assist",
            "player_attack_depth_tolerance",
            "player_attack_temporal_forgiveness",
            "player_attack_elevation_forgiveness",
            "player_attack_rear_tolerance",
            "enemy_attack_rear_tolerance",
        )
        for field in nonnegative_physics:
            with self.subTest(physics_field=field):
                invalid = deepcopy(self.data)
                invalid["engine"]["physics"][field] = -0.01
                with self.assertRaisesRegex(ConfigError, rf"physics\.{field}"):
                    validate_gameplay(invalid)

        for field in ("light_hitstop", "heavy_hitstop", "super_hitstop"):
            with self.subTest(hitstop_field=field):
                invalid = deepcopy(self.data)
                invalid["engine"]["physics"][field] = 0
                with self.assertRaisesRegex(ConfigError, rf"physics\.{field}"):
                    validate_gameplay(invalid)

        invalid_enemy = deepcopy(self.data)
        invalid_enemy["enemies"]["stick"]["active"] = 0
        with self.assertRaisesRegex(ConfigError, r"enemies\.stick\.active"):
            validate_gameplay(invalid_enemy)

        invalid_scoring = deepcopy(self.data)
        invalid_scoring["scoring"]["combo_step_hits"] = 0
        with self.assertRaisesRegex(ConfigError, r"scoring\.combo_step_hits"):
            validate_gameplay(invalid_scoring)

        invalid_dodge_window = deepcopy(self.data)
        invalid_dodge_window["players"]["global"]["dodge_invulnerable"] = (
            invalid_dodge_window["players"]["global"]["dodge_duration"] + 0.01
        )
        with self.assertRaisesRegex(ConfigError, "cannot exceed dodge_duration"):
            validate_gameplay(invalid_dodge_window)

    def test_optional_move_combat_tuning_is_strict_when_present(self) -> None:
        valid = deepcopy(self.data)
        move = valid["moves"]["light_combo"][0]
        active_end = move["startup"] + move["active"]
        move.update(
            {
                "buffer_window": 0.12,
                "cancel_start": active_end,
                "max_hits_per_target": 1,
                "max_targets": 2,
                "rehit_delay": 0.0,
                "reach_forgiveness": 2.0,
                "depth_forgiveness": 1.0,
                "temporal_forgiveness": 0.02,
                "elevation_forgiveness": 0.0,
                "lane_assist": 3.0,
                "aim_range_bonus": 4.0,
                "lunge": 0.0,
                "rear_tolerance": 3.0,
                "hit_downed": False,
                "chain_on_whiff": True,
                "heavy_cancel": False,
            }
        )
        validate_gameplay(valid)

        invalid_values = {
            "buffer_window": 0,
            "cancel_start": active_end - 0.001,
            "max_hits_per_target": 0,
            "max_targets": True,
            "rehit_delay": -0.01,
            "reach_forgiveness": -0.01,
            "depth_forgiveness": -0.01,
            "temporal_forgiveness": -0.01,
            "elevation_forgiveness": -0.01,
            "lane_assist": -0.01,
            "aim_range_bonus": -0.01,
            "lunge": -0.01,
            "rear_tolerance": -0.01,
            "hit_downed": 1,
            "chain_on_whiff": "yes",
            "heavy_cancel": None,
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                invalid = deepcopy(self.data)
                invalid["moves"]["light_combo"][0][field] = value
                with self.assertRaisesRegex(
                    ConfigError, rf"moves\.light_combo\[0\]\.{field}"
                ):
                    validate_gameplay(invalid)

    def test_optional_hitbox_frames_require_normalized_ordered_finite_samples(self) -> None:
        valid_frames = [
            {
                "at": 0.0,
                "reach_scale": 0.8,
                "depth_scale": 1.0,
                "height_scale": 1.0,
                "offset_x": -2.0,
            },
            {
                "at": 0.5,
                "reach_scale": 1.1,
                "depth_scale": 1.05,
                "height_scale": 1.0,
                "depth_offset": 1.0,
            },
            {
                "at": 1.0,
                "reach_scale": 0.9,
                "depth_scale": 1.0,
                "height_scale": 0.95,
                "elevation_offset": 0.0,
            },
        ]
        valid = deepcopy(self.data)
        valid["moves"]["heavy"]["hitbox_frames"] = deepcopy(valid_frames)
        validate_gameplay(valid)

        invalid_frame_sets = {
            "missing_start": [dict(frame) for frame in valid_frames],
            "missing_end": [dict(frame) for frame in valid_frames],
            "unordered": [dict(frame) for frame in valid_frames],
            "bad_scale": [dict(frame) for frame in valid_frames],
            "bad_offset": [dict(frame) for frame in valid_frames],
        }
        invalid_frame_sets["missing_start"][0]["at"] = 0.1
        invalid_frame_sets["missing_end"][-1]["at"] = 0.9
        invalid_frame_sets["unordered"][1]["at"] = 0.0
        invalid_frame_sets["bad_scale"][1]["reach_scale"] = 0
        invalid_frame_sets["bad_offset"][1]["depth_offset"] = float("inf")

        for case, frames in invalid_frame_sets.items():
            with self.subTest(case=case):
                invalid = deepcopy(self.data)
                invalid["moves"]["heavy"]["hitbox_frames"] = frames
                with self.assertRaisesRegex(
                    ConfigError, r"moves\.heavy\.hitbox_frames"
                ):
                    validate_gameplay(invalid)

    def test_audio_transition_and_completion_tuning_fail_fast(self) -> None:
        duplicate_music = deepcopy(self.data)
        duplicate_music["audio"]["stage_music"] = duplicate_music["audio"]["menu_music"]
        with self.assertRaisesRegex(ConfigError, "distinct"):
            validate_gameplay(duplicate_music)

        invalid_transition = deepcopy(self.data)
        invalid_transition["transitions"]["boss_loading"]["relocate_seconds"] = 9.0
        with self.assertRaisesRegex(ConfigError, "relocation"):
            validate_gameplay(invalid_transition)

        invalid_treats = deepcopy(self.data)
        invalid_treats["completion"]["treat_release_seconds"] = 5.0
        with self.assertRaisesRegex(ConfigError, "release treats"):
            validate_gameplay(invalid_treats)

    def test_external_json_saved_with_utf8_bom_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "tuning.json"
            path.write_text(json.dumps({"chief": {"command_cost": 50}}), encoding="utf-8-sig")
            with patch("src.config.resource_path", return_value=path):
                self.assertEqual(load_json("data/gameplay.json")["chief"]["command_cost"], 50)

    def test_resource_resolution_uses_one_validated_root_without_file_mixing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            override = root / "override"
            packaged = root / "packaged"
            (override / "assets").mkdir(parents=True)
            (override / "data").mkdir()
            (packaged / "assets").mkdir(parents=True)
            (packaged / "data").mkdir()
            live = override / "assets" / "live.bin"
            live.write_bytes(b"canonical")
            (packaged / "assets" / "package-only.bin").write_bytes(b"must-not-mix")
            (packaged / "data" / "gameplay.json").write_text("{}", encoding="utf-8")
            manifest = {
                "files": [
                    {
                        "path": "assets/live.bin",
                        "size": live.stat().st_size,
                        "sha256": hashlib.sha256(live.read_bytes()).hexdigest(),
                    }
                ]
            }
            (override / "data" / "content-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            clear_resource_root_cache()
            try:
                with (
                    patch.dict(os.environ, {CONTENT_ROOT_ENV: str(override)}, clear=False),
                    patch("src.config.executable_root", return_value=packaged),
                ):
                    self.assertEqual(active_resource_root(), override.resolve())
                    self.assertEqual(resource_path("assets/live.bin"), live.resolve())
                    with self.assertRaises(FileNotFoundError):
                        resource_path("assets/package-only.bin")
            finally:
                clear_resource_root_cache()


if __name__ == "__main__":
    unittest.main()
