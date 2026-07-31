"""Download and activate shared content updates for all platforms."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CONTENT_MANIFEST_PATH, content_root


DEFAULT_FEED_URL = (
    "https://api.github.com/repos/hughbechainez-byte/the-fades-of-fate/releases/latest"
)
DEFAULT_USER_AGENT = "The Fades of Fate Content Updater"
MANIFEST_ASSET_NAME = "fades-of-fate-content-manifest.json"
PACK_ASSET_NAME = "fades-of-fate-content-pack.zip"


class ContentUpdateError(RuntimeError):
    """Raised when online or on-device content synchronization fails."""


@dataclass(frozen=True)
class UpdateResult:
    status: str
    updated: bool
    content_root: str
    local_revision: int
    remote_revision: int
    manifest_path: str
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "updated": self.updated,
            "content_root": self.content_root,
            "local_revision": self.local_revision,
            "remote_revision": self.remote_revision,
            "manifest_path": self.manifest_path,
            "reason": self.reason,
        }


def _safe_int(value: Any, default: int) -> int:
    try:
        value_int = int(value)
        if value_int >= 0:
            return value_int
    except (TypeError, ValueError):
        pass
    return default


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ContentUpdateError(f"manifest payload is not an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131_072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _http_json(url: str, timeout: float, user_agent: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, context=ssl.create_default_context(), timeout=timeout) as response:
            data = response.read()
    except urllib.error.URLError as exc:
        raise ContentUpdateError(f"update request failed for {url}: {exc}") from exc
    try:
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ContentUpdateError(f"manifest response was not valid JSON from {url}") from exc


def _http_download(url: str, destination: Path, timeout: float, user_agent: str) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(request, context=ssl.create_default_context(), timeout=timeout) as response:
            destination.write_bytes(response.read())
    except urllib.error.URLError as exc:
        raise ContentUpdateError(f"download failed from {url}") from exc


def _manifest_path(root: Path) -> Path:
    return root / CONTENT_MANIFEST_PATH


def _read_local_revision(root: Path) -> int:
    path = _manifest_path(root)
    if not path.is_file():
        return 0
    try:
        return _safe_int(_read_json(path).get("content_revision"), 0)
    except ContentUpdateError:
        return 0


def _asset_url_for_name(assets: list[Any], name: str) -> str:
    for asset in assets:
        if (
            isinstance(asset, dict)
            and str(asset.get("name", "")).strip().lower() == name.lower()
        ):
            url = str(asset.get("browser_download_url", "")).strip()
            if url:
                return url
    raise ContentUpdateError(f"release does not include required asset {name!r}")


def _extract_package(zip_path: Path, stage_root: Path) -> None:
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(stage_root)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ContentUpdateError(f"failed to unzip downloaded content pack: {zip_path}") from exc


def _activate_content(staged_root: Path, target_root: Path) -> None:
    backup_root = target_root.with_name(f"{target_root.name}.backup")
    staged_path = staged_root
    try:
        if target_root.exists():
            if backup_root.exists():
                shutil.rmtree(backup_root)
            target_root.rename(backup_root)
        staged_path.rename(target_root)
        if backup_root.exists():
            shutil.rmtree(backup_root)
    except Exception:
        if backup_root.exists() and not target_root.exists() and staged_path.exists():
            try:
                staged_path.rename(target_root)
            except Exception:
                pass
        raise


def apply_content_update_if_available(
    content_root_override: str | None = None,
    *,
    game_version: str | None = None,
    feed_url: str = DEFAULT_FEED_URL,
    timeout_seconds: float = 6.0,
    manifest_asset_name: str = MANIFEST_ASSET_NAME,
    pack_asset_name: str = PACK_ASSET_NAME,
    user_agent: str = DEFAULT_USER_AGENT,
) -> UpdateResult:
    """Check release metadata and apply a full content pack when newer than local."""
    override_root = content_root_override.strip() if content_root_override else None
    target_root = content_root() if not override_root else Path(override_root).expanduser().resolve()
    if feed_url is None:
        feed_url = os.environ.get("FADES_OF_FATE_CONTENT_FEED", DEFAULT_FEED_URL)
    feed_url = feed_url.strip() or DEFAULT_FEED_URL

    if timeout_seconds <= 0:
        timeout_seconds = 1.0

    local_revision = _read_local_revision(target_root)
    try:
        release_payload = _http_json(feed_url, timeout_seconds, user_agent)
    except ContentUpdateError:
        return UpdateResult(
            status="failed",
            updated=False,
            content_root=str(target_root),
            local_revision=local_revision,
            remote_revision=local_revision,
            manifest_path=str(_manifest_path(target_root)),
            reason="release feed unavailable",
        )

    assets = release_payload.get("assets")
    if not isinstance(assets, list):
        raise ContentUpdateError("release payload has no assets list")

    manifest_url = _asset_url_for_name(assets, manifest_asset_name)
    pack_url = _asset_url_for_name(assets, pack_asset_name)
    try:
        manifest = _http_json(manifest_url, timeout_seconds, user_agent)
    except ContentUpdateError as exc:
        raise ContentUpdateError(f"could not download update manifest: {exc}") from exc

    remote_revision = _safe_int(manifest.get("content_revision"), 0)
    remote_version = str(manifest.get("minimum_game_version", "")).strip()
    if game_version is not None and remote_version and remote_version != game_version:
        return UpdateResult(
            status="skipped",
            updated=False,
            content_root=str(target_root),
            local_revision=local_revision,
            remote_revision=remote_revision,
            manifest_path=str(_manifest_path(target_root)),
            reason="requires matching game version",
        )

    if remote_revision <= local_revision:
        return UpdateResult(
            status="up_to_date",
            updated=False,
            content_root=str(target_root),
            local_revision=local_revision,
            remote_revision=remote_revision,
            manifest_path=str(_manifest_path(target_root)),
            reason="content already current",
        )

    with tempfile.TemporaryDirectory(prefix="fades-content-update-") as stage:
        stage_root = Path(stage).resolve()
        staged_pack = stage_root / "content-pack.zip"
        _http_download(pack_url, staged_pack, timeout_seconds, user_agent)
        expected = str(manifest.get("pack", {}).get("sha256", "")).strip().lower()
        if expected:
            actual = _sha256(staged_pack)
            if actual != expected:
                raise ContentUpdateError(
                    f"pack hash mismatch: expected {expected}, got {actual}"
                )

        unpack_root = stage_root / "unpacked"
        unpack_root.mkdir(parents=True, exist_ok=True)
        _extract_package(staged_pack, unpack_root)
        staged_manifest = unpack_root / "data" / "content-manifest.json"
        if not staged_manifest.is_file():
            _write_json(unpack_root / "data" / "content-manifest.json", manifest)
        _activate_content(unpack_root, target_root)

    _write_json(_manifest_path(target_root), manifest)
    return UpdateResult(
        status="updated",
        updated=True,
        content_root=str(target_root),
        local_revision=local_revision,
        remote_revision=remote_revision,
        manifest_path=str(_manifest_path(target_root)),
        reason="update applied",
    )
