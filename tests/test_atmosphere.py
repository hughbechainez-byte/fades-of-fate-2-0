"""Atmospheric state determinism and save-contract tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from src.atmosphere import AtmosphereSnapshot, AtmosphereState
from src.progression import (
    DEFAULT_FIRST_LEVEL_ID,
    GameOptions,
    ProgressionState,
    ReplayStats,
    RunStats,
    SaveData,
    SaveRepository,
)


def _new_sample_save() -> SaveData:
    run = RunStats(
        completed=True,
        score=4500,
        completion_seconds=77.0,
        kos=9,
        hits_landed=33,
        damage_taken=6.5,
        rank="A",
        difficulty="normal",
    )
    progression = ProgressionState.new(DEFAULT_FIRST_LEVEL_ID).record_run(
        DEFAULT_FIRST_LEVEL_ID,
        run,
        next_level_id="chapter_1_level_2",
    )
    atmosphere = AtmosphereState.new(seed=1234)
    atmosphere.set_target_profile("i8_underpass_dimming")
    atmosphere.advance(0.75)
    return SaveData(
        options=GameOptions.from_preset("cinematic"),
        progression=progression,
        atmosphere=atmosphere,
    )


class AtmosphereSnapshotTests(unittest.TestCase):
    def test_invalid_profiles_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AtmosphereState.from_mapping({"current_profile_id": "not-found"})
        with self.assertRaises(ValueError):
            AtmosphereState.new().set_target_profile("does-not-exist")


class AtmosphereStateTests(unittest.TestCase):
    def test_determinism_holds_across_update_partitions(self) -> None:
        state_a = AtmosphereState.new(seed=99, profile_id="chapter_1_sunset")
        state_b = AtmosphereState.new(seed=99, profile_id="chapter_1_sunset")
        state_a.set_target_profile("i8_underpass_dimming")
        state_b.set_target_profile("i8_underpass_dimming")

        state_a.advance(0.75)
        state_b.advance(0.25)
        state_b.advance(0.25)
        state_b.advance(0.25)

        self.assertEqual(state_a.snapshot(), state_b.snapshot())

    def test_pause_halts_state_changes(self) -> None:
        state = AtmosphereState.new(seed=777)
        state.set_target_profile("i8_underpass_dimming")
        frozen = state.snapshot()

        state.advance(1.5, paused=True)

        self.assertEqual(state.snapshot(), frozen)
        state.advance(1.5, paused=False)
        self.assertNotEqual(state.time_seconds, frozen.time_seconds)

    def test_stage_transition_continuity(self) -> None:
        state = AtmosphereState.new(seed=555, profile_id="chapter_1_sunset")
        state.set_target_profile("i8_underpass_dimming")
        state.advance(0.5)
        mid = state.snapshot()

        state.set_profile_for_route("chapter_1_level_4")
        state.advance(0.5)
        after = state.snapshot()

        self.assertEqual(state.current_profile_id, "chapter_1_sunset")
        self.assertEqual(state.target_profile_id, "awaken_finale")
        self.assertTrue(after.time_seconds > mid.time_seconds)
        self.assertNotEqual(after.cloud_phases, AtmosphereState.new(seed=555).cloud_phases)
        self.assertNotEqual(after.cloud_phases, mid.cloud_phases)

    def test_transition_reaches_target(self) -> None:
        state = AtmosphereState.new(seed=321, profile_id="chapter_1_sunset")
        state.set_target_profile("awaken_finale")
        state.advance(20.0)

        self.assertEqual(state.current_profile_id, "awaken_finale")
        self.assertEqual(state.target_profile_id, "awaken_finale")
        self.assertEqual(state.transition_progress, 1.0)
        snapshot = state.snapshot()
        self.assertEqual(snapshot.current_profile_id, "awaken_finale")

    def test_stable_seed_restoration(self) -> None:
        def stepped(seed: int) -> AtmosphereSnapshot:
            state = AtmosphereState.new(seed=seed, profile_id="chapter_1_sunset")
            state.set_target_profile("i8_underpass_dimming")
            state.advance(3.0)
            return state.snapshot()

        self.assertEqual(stepped(111), stepped(111))
        self.assertNotEqual(stepped(111), stepped(222))


class AtmosphereSaveTests(unittest.TestCase):
    def test_save_round_trip_includes_atmosphere(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "save.json"
            repository = SaveRepository(path)
            sample = _new_sample_save()
            repository.save(sample)
            loaded = repository.load(default=sample).data

            self.assertEqual(loaded.atmosphere, sample.atmosphere)

    def test_old_save_with_no_atmosphere_key_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "save.json"
            legacy = {
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
            }
            path.write_text(json.dumps(legacy), encoding="utf-8")

            loaded = SaveRepository(path).load().data

            self.assertEqual(loaded.atmosphere.current_profile_id, AtmosphereState.new().current_profile_id)
            self.assertEqual(loaded.atmosphere.transition_progress, 1.0)


if __name__ == "__main__":
    unittest.main()
