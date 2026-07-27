from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.audio import AudioManager


class _MusicStream:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.busy = False

    def get_busy(self) -> bool:
        return self.busy

    def stop(self) -> None:
        self.calls.append(("stop", None))
        self.busy = False

    def unload(self) -> None:
        self.calls.append(("unload", None))

    def load(self, path: str) -> None:
        self.calls.append(("load", Path(path).name))

    def set_volume(self, volume: float) -> None:
        self.calls.append(("volume", volume))

    def play(self, loops: int) -> None:
        self.calls.append(("play", loops))
        self.busy = True


class MusicHandoffTests(unittest.TestCase):
    def test_replacing_music_hard_stops_before_loading_and_skips_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "menu.ogg").touch()
            (root / "stage.ogg").touch()
            stream = _MusicStream()
            manager = AudioManager(assets_directory=root)
            manager.available = True
            manager._initialized = True
            manager._pygame = SimpleNamespace(mixer=SimpleNamespace(music=stream))

            self.assertTrue(manager.play_music_file("menu.ogg"))
            self.assertEqual(stream.calls[:2], [("stop", None), ("unload", None)])
            first_call_count = len(stream.calls)
            self.assertTrue(manager.play_music_file("menu.ogg"))
            self.assertEqual(len(stream.calls), first_call_count)
            self.assertTrue(manager.play_music_file("stage.ogg"))
            replacement = stream.calls[first_call_count:]
            self.assertEqual(replacement[:2], [("stop", None), ("unload", None)])
            self.assertEqual(manager.current_track, "stage.ogg")

    def test_multiple_managers_share_one_logical_music_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "menu.ogg").touch()
            (root / "stage.ogg").touch()
            stream = _MusicStream()
            pygame_stub = SimpleNamespace(mixer=SimpleNamespace(music=stream))
            first = AudioManager(assets_directory=root)
            second = AudioManager(assets_directory=root)
            for manager in (first, second):
                manager.available = True
                manager._initialized = True
                manager._pygame = pygame_stub

            self.assertTrue(first.play_music_file("menu.ogg"))
            menu_calls = len(stream.calls)
            self.assertTrue(second.play_music_file("menu.ogg"))
            self.assertEqual(len(stream.calls), menu_calls)
            self.assertIsNone(first.current_track)
            self.assertEqual(second.current_track, "menu.ogg")

            self.assertTrue(first.play_music_file("stage.ogg"))
            self.assertIsNone(second.current_track)
            self.assertEqual(first.current_track, "stage.ogg")
            self.assertEqual(
                stream.calls[menu_calls:menu_calls + 3],
                [("stop", None), ("unload", None), ("load", "stage.ogg")],
            )


if __name__ == "__main__":
    unittest.main()
