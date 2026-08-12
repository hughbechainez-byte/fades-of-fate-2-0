from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from src import config


class AndroidStartupTests(unittest.TestCase):
    def test_android_runtime_uses_private_app_storage(self) -> None:
        with TemporaryDirectory() as private_dir:
            with mock.patch.dict(
                os.environ,
                {
                    "ANDROID_PRIVATE": private_dir,
                    "ANDROID_ARGUMENT": "",
                    "ANDROID_ROOT": "/android",
                    "FADES_OF_FATE_CONTENT_ROOT": "",
                },
                clear=False,
            ):
                self.assertTrue(config.is_android_runtime())
                self.assertEqual(config.android_private_root(), Path(private_dir).resolve())
                self.assertEqual(
                    config.content_root(),
                    (Path(private_dir) / "the-fades-of-fate" / "content").resolve(),
                )

    def test_desktop_runtime_does_not_select_android_storage(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "ANDROID_PRIVATE": "",
                "ANDROID_ARGUMENT": "",
                "ANDROID_ROOT": "",
            },
            clear=False,
        ):
            self.assertFalse(config.is_android_runtime())
            self.assertIsNone(config.android_private_root())


if __name__ == "__main__":
    unittest.main()
