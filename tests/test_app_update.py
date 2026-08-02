from __future__ import annotations

import unittest
from unittest.mock import patch

from src.app_update import (
    AppUpdateError,
    AppUpdateManifest,
    check_app_update,
)


class AppUpdateTests(unittest.TestCase):
    def _loader(self, payloads: dict[str, dict[str, object]]):
        def load(url: str, timeout: float, user_agent: str) -> dict[str, object]:
            self.assertGreater(timeout, 0)
            self.assertTrue(user_agent)
            return payloads[url]

        return load

    def _payloads(self, version: str = "0.15.2") -> dict[str, dict[str, object]]:
        feed = "https://api.github.com/repos/hughbechainez-byte/the-fades-of-fate/releases/latest"
        manifest_url = "https://github.com/hughbechainez-byte/the-fades-of-fate/releases/download/v0.15.2/fades-of-fate-app-manifest.json"
        package_url = "https://github.com/hughbechainez-byte/the-fades-of-fate/releases/download/v0.15.2/The-Fades-of-Fate-v0.15.2-Windows-x64.zip"
        return {
            feed: {
                "assets": [
                    {"name": "fades-of-fate-app-manifest.json", "browser_download_url": manifest_url},
                    {"name": "The-Fades-of-Fate-v0.15.2-Windows-x64.zip", "browser_download_url": package_url},
                ]
            },
            manifest_url: {
                "schema_version": 1,
                "product": "The Fades of Fate",
                "platform": "windows-x64",
                "version": version,
                "release_tag": "v0.15.2",
                "package_asset_name": "The-Fades-of-Fate-v0.15.2-Windows-x64.zip",
                "package_url": package_url,
                "package_sha256": "a" * 64,
                "package_size": 123,
            },
        }

    def test_new_release_is_available_from_manifest(self) -> None:
        with patch("src.app_update.os.name", "nt"):
            result = check_app_update(
                "0.15.1-motorola-startup-fix",
                http_json=self._loader(self._payloads()),
            )
        self.assertEqual(result.status, "available")
        self.assertTrue(result.available)
        self.assertEqual(result.latest_version, "0.15.2")
        self.assertIsNotNone(result.manifest)

    def test_same_release_is_up_to_date(self) -> None:
        with patch("src.app_update.os.name", "nt"):
            result = check_app_update(
                "0.15.2",
                http_json=self._loader(self._payloads()),
            )
        self.assertEqual(result.status, "up_to_date")
        self.assertFalse(result.available)

    def test_manifest_rejects_non_github_package_url(self) -> None:
        payload = self._payloads()[
            "https://github.com/hughbechainez-byte/the-fades-of-fate/releases/download/v0.15.2/fades-of-fate-app-manifest.json"
        ]
        payload["package_url"] = "https://example.com/game.zip"
        with self.assertRaises(AppUpdateError):
            AppUpdateManifest.from_mapping(payload)

    def test_latest_release_check_rejects_untrusted_feed(self) -> None:
        with patch("src.app_update.os.name", "nt"):
            result = check_app_update("0.15.1", feed_url="https://example.com/latest")
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.available)

    def test_non_windows_host_is_explicitly_unsupported(self) -> None:
        with patch("src.app_update.os.name", "posix"):
            result = check_app_update("0.15.2")
        self.assertEqual(result.status, "unsupported")
        self.assertFalse(result.available)


if __name__ == "__main__":
    unittest.main()
