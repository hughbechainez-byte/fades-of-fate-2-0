from __future__ import annotations

import unittest

from src.config import load_gameplay, resource_path


class MusicAssetTests(unittest.TestCase):
    def test_requested_friday_activities_title_track_is_packaged(self) -> None:
        path = resource_path("assets/audio/friday_activities_klickaud_menu.ogg")
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 100_000)
        self.assertEqual(path.read_bytes()[:4], b"OggS")

    def test_menu_and_stage_use_distinct_packaged_tracks(self) -> None:
        audio = load_gameplay()["audio"]
        self.assertEqual(audio["menu_music"], "friday_activities_klickaud_menu.ogg")
        self.assertEqual(audio["stage_music"], "red_2nd_track_stage_8bit.ogg")
        self.assertNotEqual(audio["menu_music"], audio["stage_music"])
        for key in ("menu_music", "stage_music"):
            path = resource_path(f"assets/audio/{audio[key]}")
            with self.subTest(track=key):
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 100_000)
                self.assertEqual(path.read_bytes()[:4], b"OggS")


if __name__ == "__main__":
    unittest.main()
