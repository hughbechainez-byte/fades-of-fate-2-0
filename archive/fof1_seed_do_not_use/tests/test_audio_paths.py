from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.audio import _assets_directory


class AudioPathTests(unittest.TestCase):
    def test_packaged_external_audio_overrides_bundled_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            external = root / "game" / "assets" / "audio"
            internal = root / "bundle" / "assets" / "audio"
            external.mkdir(parents=True)
            internal.mkdir(parents=True)
            executable = root / "game" / "The Fades of Fate.exe"
            with (
                mock.patch.object(sys, "frozen", True, create=True),
                mock.patch.object(sys, "executable", str(executable)),
                mock.patch.object(sys, "_MEIPASS", str(root / "bundle"), create=True),
            ):
                self.assertEqual(_assets_directory(), external.resolve())


if __name__ == "__main__":
    unittest.main()
