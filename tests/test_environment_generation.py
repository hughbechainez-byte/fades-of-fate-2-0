"""Contracts for the deterministic environment authoring layer."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.environment_generation import (  # noqa: E402
    EnvironmentGenerator,
    EnvironmentLibrary,
    load_library,
    load_recipe,
)
from src.stage_world import StageWorld  # noqa: E402


class EnvironmentGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.library = load_library(PROJECT_ROOT)

    def test_approved_library_is_fail_closed_and_dimension_checked(self) -> None:
        report = self.library.validate_all("fades_environment_v1")
        self.assertTrue(report.passed, report.as_dict())
        module = self.library.module("market_secondary_architecture")
        denied = replace(module, source="assets/stage/placeholder_facade.png")
        denied_report = self.library.validate_module(denied, self.library.style("fades_environment_v1"))
        self.assertFalse(denied_report.passed)
        self.assertTrue(any(issue.code == "asset.denied" for issue in denied_report.errors))
        wrong_size = replace(module, native_dimensions=(1, 1))
        wrong_size_report = self.library.validate_module(wrong_size, self.library.style("fades_environment_v1"))
        self.assertFalse(wrong_size_report.passed)
        self.assertTrue(any(issue.code == "asset.dimensions" for issue in wrong_size_report.errors))

    def test_same_seed_is_byte_stable_and_other_seeds_vary(self) -> None:
        recipe = load_recipe(PROJECT_ROOT / "data/content-generation/recipes/civic_hall_dusk.json")
        first = EnvironmentGenerator(self.library, recipe, seed=1729).generate()
        second = EnvironmentGenerator(self.library, recipe, seed=1729).generate()
        other = EnvironmentGenerator(self.library, recipe, seed=1730).generate()
        self.assertEqual(first, second)
        self.assertNotEqual(first["manifest_sha256"], other["manifest_sha256"])
        self.assertTrue(EnvironmentGenerator(self.library, recipe, seed=1729).validate_manifest(first).passed)

    def test_civic_proof_has_two_interactive_types_and_true_layers(self) -> None:
        recipe = load_recipe(PROJECT_ROOT / "data/content-generation/recipes/civic_hall_dusk.json")
        manifest = EnvironmentGenerator(self.library, recipe).generate()
        report = EnvironmentGenerator(self.library, recipe).validate_manifest(manifest)
        self.assertTrue(report.passed, report.as_dict())
        interactive = {
            self.library.module(placement["module_id"]).module_id
            for placement in manifest["placements"]
            if self.library.module(placement["module_id"]).category in {"interactive", "hazard", "pickup", "throwable"}
        }
        self.assertGreaterEqual(len(interactive), 2)
        layers = {placement["layer"] for placement in manifest["placements"]}
        self.assertTrue({"sky", "far", "mid", "ground", "foreground"}.issubset(layers))
        self.assertEqual(manifest["repetition_report"]["passed"], True)

    def test_native_stage_world_adapter_is_accepted_by_existing_loader(self) -> None:
        recipe = load_recipe(PROJECT_ROOT / "data/content-generation/recipes/neighborhood_market_sunset.json")
        manifest = EnvironmentGenerator(self.library, recipe).generate()
        native = manifest["native_stage_world"]
        route = native["routes"][0]
        world = StageWorld.from_route(route, native)
        self.assertEqual(world.world_width, recipe.target_length)
        self.assertEqual(len(world.chunks), len(recipe.zones))
        self.assertEqual(world.asset_paths()[0].startswith("assets/"), True)

    def test_unsupported_runtime_scale_is_rejected(self) -> None:
        module = self.library.module("authored_planter_cluster")
        report = self.library.validate_module(replace(module, scale=2), self.library.style("fades_environment_v1"))
        self.assertFalse(report.passed)
        self.assertTrue(any(issue.code == "unsupported.scale" for issue in report.errors))

    def test_checked_in_proof_manifest_revalidates(self) -> None:
        recipe = load_recipe(PROJECT_ROOT / "data/content-generation/recipes/civic_hall_dusk.json")
        path = PROJECT_ROOT / "data/content-generation/generated/civic_hall_dusk_manifest.json"
        if not path.is_file():
            self.skipTest("generated proof manifest has not been baked")
        payload = json.loads(path.read_text(encoding="utf-8"))
        report = EnvironmentGenerator(self.library, recipe).validate_manifest(payload)
        self.assertTrue(report.passed, report.as_dict())


if __name__ == "__main__":
    unittest.main()
