"""The people/setpiece visual contract stays explicit and machine-checkable."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CharacterArtStyleStandardTests(unittest.TestCase):
    def test_underpass_calibration_declares_shared_people_and_setpiece_rules(self) -> None:
        standard = json.loads((ROOT / "data/character_art_style_standard.json").read_text(encoding="utf-8"))
        self.assertEqual(standard["logical_canvas"], [640, 360])
        self.assertEqual(standard["calibration_profile"]["id"], "cool_underpass_dusk_v1")
        self.assertIn("grounding", standard["character_rules"])
        self.assertIn("lighting", standard["setpiece_rules"])
        self.assertEqual(standard["calibration_profile"]["highlight_limit"], [232, 232, 238])


if __name__ == "__main__":
    unittest.main()
