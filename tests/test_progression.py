"""Deterministic save, option-preset, progression, and replay contracts."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.level_complete import CompletionStats
from src.progression import (
    DEFAULT_FIRST_LEVEL_ID,
    GameOptions,
    ProgressionState,
    AtmosphereState,
    QUALITY_PRESETS,
    QUALITY_PRESET_NAMES,
    ReplayStats,
    RunStats,
    SAVE_SCHEMA_VERSION,
    SaveData,
    SaveRepository,
)


class GameOptionsTests(unittest.TestCase):
    def test_quality_presets_cover_performance_cinematic_and_accessibility_needs(self) -> None:
        self.assertEqual(tuple(QUALITY_PRESETS), QUALITY_PRESET_NAMES)
        performance = QUALITY_PRESETS["performance"]
        balanced = QUALITY_PRESETS["balanced"]
        cinematic = QUALITY_PRESETS["cinematic"]
        accessible = QUALITY_PRESETS["accessible"]

        self.assertLess(performance.particle_density, balanced.particle_density)
        self.assertLess(balanced.particle_density, cinematic.particle_density)
        self.assertLess(performance.shake_intensity, cinematic.shake_intensity)
        self.assertGreater(accessible.hud_scale, balanced.hud_scale)
        self.assertEqual(accessible.hud_opacity, 1.0)
        self.assertLess(accessible.shake_intensity, balanced.shake_intensity)
        self.assertLess(accessible.flash_intensity, balanced.flash_intensity)
        self.assertTrue(accessible.high_contrast)
        self.assertTrue(accessible.pickup_outline)
        with self.assertRaises(TypeError):
            QUALITY_PRESETS["new"] = balanced  # type: ignore[index]

    def test_preset_changes_preserve_difficulty_and_manual_changes_become_custom(self) -> None:
        options = GameOptions.from_preset("cinematic", difficulty="hard")
        custom = options.with_overrides(hud_scale=1.25, flash_intensity=0.4)
        performance = custom.apply_preset("performance")

        self.assertEqual(custom.quality_preset, "custom")
        self.assertEqual(custom.difficulty, "hard")
        self.assertEqual(custom.hud_scale, 1.25)
        self.assertEqual(performance.quality_preset, "performance")
        self.assertEqual(performance.difficulty, "hard")
        self.assertEqual(
            options.with_overrides(difficulty="story").quality_preset,
            "cinematic",
        )

    def test_option_mappings_ignore_future_keys_but_reject_bad_saved_values(self) -> None:
        loaded = GameOptions.from_mapping(
            {
                "quality_preset": "accessible",
                "hud_scale": 1.3,
                "difficulty": "story",
                "future_option": "ignored",
            }
        )
        self.assertEqual(loaded.quality_preset, "accessible")
        self.assertEqual(loaded.hud_scale, 1.3)
        self.assertEqual(loaded.difficulty, "story")

        invalid_factories = (
            lambda: GameOptions(hud_scale=0.79),
            lambda: GameOptions(hud_opacity=1.01),
            lambda: GameOptions(shake_intensity=-0.01),
            lambda: GameOptions(flash_intensity=1.01),
            lambda: GameOptions(particle_density=0.24),
            lambda: GameOptions(dialogue_speed=float("nan")),
            lambda: GameOptions(high_contrast=1),
            lambda: GameOptions(difficulty="nightmare"),
            lambda: GameOptions.from_preset("ultra"),
            lambda: GameOptions.from_preset("balanced", future_option=True),
            lambda: GameOptions.from_mapping([]),
            lambda: GameOptions.from_mapping({"quality_preset": "unknown"}),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory):
                with self.assertRaises(ValueError):
                    factory()


class ProgressionTests(unittest.TestCase):
    def test_completion_stats_adapter_matches_the_existing_results_contract(self) -> None:
        completion = CompletionStats(
            completion_seconds=84.25,
            combined_score=4200,
            kos=11,
            hits_landed=76,
            damage_taken=18.5,
            rating_points=6100,
            rank="A",
        )

        run = RunStats.from_completion(completion, difficulty="hard")

        self.assertEqual(run.score, completion.combined_score)
        self.assertEqual(run.completion_seconds, completion.completion_seconds)
        self.assertEqual(run.kos, completion.kos)
        self.assertEqual(run.hits_landed, completion.hits_landed)
        self.assertEqual(run.damage_taken, completion.damage_taken)
        self.assertEqual(run.rank, completion.rank)
        self.assertEqual(run.difficulty, "hard")

    def test_attempts_aggregate_replay_stats_and_only_clears_unlock_next_level(self) -> None:
        level_one = DEFAULT_FIRST_LEVEL_ID
        level_two = "chapter_1_level_2"
        initial = ProgressionState.new()
        failed = RunStats(
            completed=False,
            score=350,
            kos=1,
            hits_landed=4,
            damage_taken=12.25,
            difficulty="story",
        )
        after_failure = initial.record_run(level_one, failed, next_level_id=level_two)
        self.assertFalse(after_failure.is_unlocked(level_two))
        self.assertEqual(after_failure.stats_for(level_one).plays, 1)
        self.assertEqual(after_failure.stats_for(level_one).clears, 0)

        first_clear = RunStats(
            completed=True,
            score=1200,
            completion_seconds=75.0,
            kos=3,
            hits_landed=20,
            damage_taken=8.0,
            rank="B",
            difficulty="hard",
        )
        second_clear = RunStats(
            completed=True,
            score=1100,
            completion_seconds=60.0,
            kos=4,
            hits_landed=25,
            damage_taken=2.5,
            rank="A",
        )
        after_first_clear = after_failure.record_run(
            level_one,
            first_clear,
            next_level_id=level_two,
        )
        final = after_first_clear.record_run(level_one, second_clear, next_level_id=level_two)
        stats = final.stats_for(level_one)

        self.assertTrue(final.is_unlocked(level_two))
        self.assertEqual(final.completed_level_ids, (level_one,))
        self.assertEqual(final.last_level_id, level_one)
        self.assertEqual(stats.plays, 3)
        self.assertEqual(stats.clears, 2)
        self.assertEqual(stats.best_score, 1200)
        self.assertEqual(stats.best_completion_seconds, 60.0)
        self.assertEqual(stats.best_rank, "A")
        self.assertEqual(stats.total_kos, 8)
        self.assertEqual(stats.total_hits_landed, 49)
        self.assertEqual(stats.total_damage_taken, 22.75)
        self.assertEqual(stats.last_score, 1100)
        self.assertEqual(stats.last_difficulty, "normal")
        self.assertEqual(initial.replay_stats, {})
        with self.assertRaises(TypeError):
            final.replay_stats[level_two] = ReplayStats()  # type: ignore[index]

    def test_progression_validation_rejects_ambiguous_sequences_and_run_types(self) -> None:
        with self.assertRaises(ValueError):
            ProgressionState(unlocked_level_ids=DEFAULT_FIRST_LEVEL_ID)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ProgressionState.from_mapping({"unlocked_level_ids": [None]})
        with self.assertRaises(TypeError):
            ProgressionState.new().record_run(DEFAULT_FIRST_LEVEL_ID, object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            ReplayStats().record(object())  # type: ignore[arg-type]


class SaveRepositoryTests(unittest.TestCase):
    @staticmethod
    def _sample_data() -> SaveData:
        options = GameOptions.from_preset("accessible", difficulty="story")
        run = RunStats(
            completed=True,
            score=7200,
            completion_seconds=52.125,
            kos=14,
            hits_landed=91,
            damage_taken=4.75,
            rank="S",
            difficulty="story",
        )
        progression = ProgressionState.new("capítulo_1").record_run(
            "capítulo_1",
            run,
            next_level_id="capítulo_2",
        )
        return SaveData(options=options, progression=progression)

    def test_mapping_round_trip_is_stable_and_forward_key_tolerant(self) -> None:
        expected = self._sample_data()
        payload = expected.to_dict()
        payload["future_root"] = {"anything": True}
        payload["options"]["future_option"] = 42
        payload["progression"]["future_progression"] = "ignored"
        payload["progression"]["replay_stats"]["capítulo_1"]["future_stat"] = 99

        loaded = SaveData.from_mapping(payload)

        self.assertEqual(loaded, expected)
        self.assertEqual(loaded.to_dict(), expected.to_dict())
        self.assertEqual(SaveData.from_mapping({}), SaveData())

    def test_bom_authored_unicode_save_loads_without_data_loss(self) -> None:
        expected = self._sample_data()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "save.json"
            path.write_text(
                json.dumps(expected.to_dict(), ensure_ascii=False),
                encoding="utf-8-sig",
            )

            result = SaveRepository(path).load()

            self.assertTrue(result.loaded)
            self.assertFalse(result.recovered)
            self.assertEqual(result.data, expected)
            self.assertIn("capítulo_2", result.data.progression.unlocked_level_ids)

    def test_atomic_write_is_bom_free_canonical_and_repeatable(self) -> None:
        expected = self._sample_data()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "save.json"
            repository = SaveRepository(path)

            repository.save(expected)
            first_bytes = path.read_bytes()
            repository.save(expected)
            second_bytes = path.read_bytes()

            self.assertEqual(first_bytes, second_bytes)
            self.assertFalse(first_bytes.startswith(b"\xef\xbb\xbf"))
            self.assertTrue(first_bytes.endswith(b"\n"))
            self.assertIn("capítulo_1", first_bytes.decode("utf-8"))
            self.assertEqual(repository.load().data, expected)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_missing_invalid_and_future_saves_return_explicit_fallback_statuses(self) -> None:
        fallback = SaveData(options=GameOptions.from_preset("performance"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "save.json"
            repository = SaveRepository(path)

            missing = repository.load(default=fallback)
            self.assertEqual(missing.status, "missing")
            self.assertIs(missing.data, fallback)
            self.assertFalse(missing.recovered)

            corrupt_bytes = b"{not-json"
            path.write_bytes(corrupt_bytes)
            invalid = repository.load(default=fallback)
            self.assertEqual(invalid.status, "invalid")
            self.assertIs(invalid.data, fallback)
            self.assertTrue(invalid.recovered)
            self.assertEqual(path.read_bytes(), corrupt_bytes)

            path.write_text("[]", encoding="utf-8")
            self.assertEqual(repository.load(default=fallback).status, "invalid")

            path.write_text(json.dumps({"schema_version": 1.5}), encoding="utf-8")
            self.assertEqual(repository.load(default=fallback).status, "invalid")

            path.write_text(
                json.dumps({"schema_version": SAVE_SCHEMA_VERSION + 1}),
                encoding="utf-8",
            )
            future = repository.load(default=fallback)
            self.assertEqual(future.status, "unsupported_version")
            self.assertIs(future.data, fallback)
            self.assertTrue(future.recovered)

    def test_failed_atomic_replace_preserves_old_save_and_removes_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "save.json"
            original = b"previous-good-save"
            path.write_bytes(original)
            repository = SaveRepository(path)

            with patch("src.progression.os.replace", side_effect=OSError("locked")):
                with self.assertRaisesRegex(OSError, "locked"):
                    repository.save(self._sample_data())

            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_schema_versions_and_repository_inputs_are_strict(self) -> None:
        for invalid_version in (True, 1.5, "1.5", -1):
            with self.subTest(invalid_version=invalid_version):
                with self.assertRaises(ValueError):
                    SaveData(schema_version=invalid_version)  # type: ignore[arg-type]
                with self.assertRaises(ValueError):
                    SaveData.from_mapping({"schema_version": invalid_version})
        self.assertEqual(
            SaveData(schema_version="1").schema_version,  # type: ignore[arg-type]
            SAVE_SCHEMA_VERSION,
        )

        with tempfile.TemporaryDirectory() as temporary:
            repository = SaveRepository(Path(temporary) / "save.json")
            with self.assertRaises(TypeError):
                repository.save(object())  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                repository.load(default=object())  # type: ignore[arg-type]

    def test_old_schema_loads_atmosphere_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "save.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "options": {
                            "quality_preset": "balanced",
                            "difficulty": "normal",
                        },
                        "progression": {
                            "unlocked_level_ids": [DEFAULT_FIRST_LEVEL_ID],
                            "completed_level_ids": [],
                            "last_level_id": None,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            loaded = SaveRepository(path).load().data

            self.assertEqual(loaded.schema_version, SAVE_SCHEMA_VERSION)
            self.assertEqual(loaded.atmosphere.current_profile_id, AtmosphereState.new().current_profile_id)
            self.assertEqual(loaded.atmosphere.target_profile_id, AtmosphereState.new().target_profile_id)


if __name__ == "__main__":
    unittest.main()
