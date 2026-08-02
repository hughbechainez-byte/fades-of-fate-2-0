import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.provenance import build_artifact_provenance, build_runtime_provenance


class ProvenanceTests(unittest.TestCase):
    def test_runtime_records_active_asset_and_scene_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "assets" / "stage").mkdir(parents=True)
            (root / "assets" / "props" / "vehicles").mkdir(parents=True)
            (root / "data" / "content-manifest.json").write_text(
                json.dumps({"content_revision": 7, "source_commit": "abc123"}),
                encoding="utf-8",
            )
            scene = root / "data" / "chapter1_location_lock.json"
            scene.write_text("{}", encoding="utf-8")
            image = root / "assets" / "stage" / "main.png"
            image.write_bytes(b"main")
            payload = build_runtime_provenance(
                root,
                game_version="test",
                platform="pc",
                level_id="chapter_1_level_1",
                route={
                    "main_panorama_asset": "assets/stage/main.png",
                    "architecture_asset": "assets/stage/missing.png",
                },
                renderer="test.renderer",
            )
            records = {item["field"]: item for item in payload["active_scenery_assets"]}
            self.assertEqual(
                records["main_panorama_asset"]["sha256"],
                hashlib.sha256(b"main").hexdigest(),
            )
            self.assertFalse(records["architecture_asset"]["resolved"])
            self.assertFalse(records["architecture_asset"]["rendered"])
            self.assertTrue(payload["all_assets_resolved"])
            self.assertEqual(payload["content_revision"], 7)
            self.assertEqual(payload["artifact_match"], "source")
            self.assertEqual(
                payload["scene_definition_sha256"],
                hashlib.sha256(b"{}").hexdigest(),
            )

    def test_artifact_match_uses_embedded_manifest_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "assets").mkdir()
            manifest = root / "data" / "content-manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            expected = hashlib.sha256(b"{}").hexdigest()
            (root / "build_provenance.json").write_text(
                json.dumps({"game_git_commit": "deadbeef", "content_manifest_sha256": expected}),
                encoding="utf-8",
            )
            payload = build_runtime_provenance(
                root,
                game_version="test",
                platform="android",
                level_id="chapter_1_level_1",
                route={},
                renderer="test.renderer",
            )
            self.assertTrue(payload["artifact_match"])
            self.assertEqual(payload["game_git_commit"], "deadbeef")

    def test_artifact_provenance_carries_pack_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = build_artifact_provenance(
                directory,
                platform="android",
                game_version="test",
                content_revision=4,
                content_manifest_sha256="manifest-hash",
                content_pack_sha256="pack-hash",
                content_pack_size=123,
            )
            self.assertEqual(payload["platform"], "android")
            self.assertEqual(payload["content_pack_sha256"], "pack-hash")
            self.assertEqual(len(payload["artifact_id"]), 64)
            self.assertFalse(payload["fallback_asset_used"])


if __name__ == "__main__":
    unittest.main()
