from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build_app_update_manifest import _version


class AppUpdateManifestBuilderTests(unittest.TestCase):
    def test_version_comes_from_canonical_version_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "version.py").write_text(
                'VERSION = "1.2.3-release"\n',
                encoding="utf-8",
            )
            (root / "src" / "game.py").write_text(
                "class FadesGame:\n    VERSION = VERSION\n",
                encoding="utf-8",
            )

            self.assertEqual(_version(root), "1.2.3-release")

    def test_nonliteral_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "version.py").write_text(
                'VERSION = make_version()\n',
                encoding="utf-8",
            )

            with self.assertRaises((ValueError, RuntimeError)):
                _version(root)


if __name__ == "__main__":
    unittest.main()
