"""Manifest-driven Windows package updater for the desktop game."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_APP_FEED_URL = (
    "https://api.github.com/repos/hughbechainez-byte/the-fades-of-fate/releases/latest"
)
DEFAULT_APP_USER_AGENT = "The Fades of Fate App Updater"
APP_MANIFEST_ASSET_NAME = "fades-of-fate-app-manifest.json"
WINDOWS_PLATFORM = "windows-x64"
PACKAGE_EXE_NAME = "The Fades of Fate.exe"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


class AppUpdateError(RuntimeError):
    """Raised when an application update manifest or package is unsafe."""


@dataclass(frozen=True)
class AppUpdateManifest:
    version: str
    release_tag: str
    package_asset_name: str
    package_sha256: str
    package_size: int
    package_url: str

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "AppUpdateManifest":
        if payload.get("schema_version") != 1:
            raise AppUpdateError("unsupported application update manifest schema")
        if str(payload.get("product", "")).strip() != "The Fades of Fate":
            raise AppUpdateError("application update manifest is for another product")
        if str(payload.get("platform", "")).strip().lower() != WINDOWS_PLATFORM:
            raise AppUpdateError("application update manifest is not for Windows x64")

        version = str(payload.get("version", "")).strip()
        release_tag = str(payload.get("release_tag", "")).strip()
        asset_name = str(payload.get("package_asset_name", "")).strip()
        package_sha256 = str(payload.get("package_sha256", "")).strip().lower()
        package_url = str(payload.get("package_url", "")).strip()
        try:
            package_size = int(payload.get("package_size", 0))
        except (TypeError, ValueError) as exc:
            raise AppUpdateError("application package size is invalid") from exc

        if not version or not release_tag or not asset_name:
            raise AppUpdateError("application update manifest is missing required fields")
        if release_tag.lstrip("vV") != version:
            raise AppUpdateError("application update version does not match its release tag")
        if not _SHA256_RE.fullmatch(package_sha256):
            raise AppUpdateError("application package hash is not SHA-256")
        if package_size <= 0:
            raise AppUpdateError("application package size must be positive")
        _validate_package_url(package_url)
        return cls(version, release_tag, asset_name, package_sha256, package_size, package_url)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "release_tag": self.release_tag,
            "package_asset_name": self.package_asset_name,
            "package_sha256": self.package_sha256,
            "package_size": self.package_size,
            "package_url": self.package_url,
        }


@dataclass(frozen=True)
class AppUpdateResult:
    status: str
    available: bool
    current_version: str
    latest_version: str
    manifest: AppUpdateManifest | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "available": self.available,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "reason": self.reason,
        }
        if self.manifest is not None:
            payload["manifest"] = self.manifest.as_dict()
        return payload


def _http_json(url: str, timeout: float, user_agent: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(
            request, context=ssl.create_default_context(), timeout=timeout
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, UnicodeError) as exc:
        raise AppUpdateError(f"update manifest request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise AppUpdateError("update manifest response was not an object")
    return payload


def _asset_url_for_name(assets: list[Any], name: str) -> str:
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if str(asset.get("name", "")).strip().lower() != name.lower():
            continue
        url = str(asset.get("browser_download_url", "")).strip()
        if url:
            return url
    raise AppUpdateError(f"release does not include required asset {name!r}")


def _validate_https_url(url: str, allowed_hosts: set[str]) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https" or parsed.hostname is None:
        raise AppUpdateError("application update URLs must use HTTPS")
    if parsed.hostname.lower() not in allowed_hosts:
        raise AppUpdateError(f"application update URL host is not trusted: {parsed.hostname}")


def _validate_package_url(url: str) -> None:
    _validate_https_url(url, {"github.com"})


def _version_key(version: str) -> tuple[tuple[int, ...], int, str]:
    """Compare the numeric release portion and then its suffix deterministically."""

    normalized = version.strip().lstrip("vV")
    numeric, _, suffix = normalized.partition("-")
    numbers = tuple(int(part) for part in numeric.split(".") if part.isdigit())
    if not numbers:
        return ((-1,), 0, normalized.lower())
    # A bare numeric release sorts after a suffixed/prerelease build.
    return (numbers, 1 if not suffix else 0, suffix.lower())


def check_app_update(
    current_version: str,
    *,
    feed_url: str = DEFAULT_APP_FEED_URL,
    timeout_seconds: float = 6.0,
    user_agent: str = DEFAULT_APP_USER_AGENT,
    http_json: Callable[[str, float, str], dict[str, Any]] | None = None,
) -> AppUpdateResult:
    """Read the latest release's signed-by-transport manifest metadata."""

    if os.name != "nt":
        return AppUpdateResult("unsupported", False, current_version, current_version, reason="Windows only")
    if timeout_seconds <= 0:
        timeout_seconds = 1.0
    feed_url = feed_url.strip() or DEFAULT_APP_FEED_URL
    loader = http_json or _http_json
    try:
        _validate_https_url(feed_url, {"api.github.com"})
        release_payload = loader(feed_url, timeout_seconds, user_agent)
        assets = release_payload.get("assets")
        if not isinstance(assets, list):
            raise AppUpdateError("latest release has no assets list")
        manifest_url = _asset_url_for_name(assets, APP_MANIFEST_ASSET_NAME)
        _validate_https_url(manifest_url, {"github.com"})
        manifest_payload = loader(manifest_url, timeout_seconds, user_agent)
        manifest = AppUpdateManifest.from_mapping(manifest_payload)
        package_url = _asset_url_for_name(assets, manifest.package_asset_name)
        _validate_package_url(package_url)
        manifest = AppUpdateManifest(
            manifest.version,
            manifest.release_tag,
            manifest.package_asset_name,
            manifest.package_sha256,
            manifest.package_size,
            package_url,
        )
    except (AppUpdateError, urllib.error.URLError) as exc:
        return AppUpdateResult(
            "failed", False, current_version, current_version, reason=str(exc)
        )

    if _version_key(manifest.version) <= _version_key(current_version):
        return AppUpdateResult(
            "up_to_date", False, current_version, manifest.version, manifest=manifest
        )
    return AppUpdateResult(
        "available", True, current_version, manifest.version, manifest=manifest
    )


def spawn_windows_updater(
    manifest: AppUpdateManifest,
    *,
    executable_root: Path,
    executable_path: Path,
    powershell_path: str = "powershell.exe",
) -> None:
    """Copy the helper outside the package and hand off before process exit."""

    if os.name != "nt":
        raise AppUpdateError("application updates are supported only on Windows")
    helper = executable_root / "tools" / "app_updater.ps1"
    if not helper.is_file():
        raise AppUpdateError(f"packaged updater helper is missing: {helper}")
    target_root = executable_path.resolve().parent
    if executable_path.name != PACKAGE_EXE_NAME or not target_root.is_dir():
        raise AppUpdateError("application update target is not the packaged Windows game")

    handoff_root = Path(tempfile.mkdtemp(prefix="fades-of-fate-update-"))
    helper_copy = handoff_root / "app_updater.ps1"
    manifest_path = handoff_root / "manifest.json"
    shutil.copy2(helper, helper_copy)
    manifest_path.write_text(json.dumps(manifest.as_dict(), indent=2), encoding="utf-8")
    try:
        subprocess.Popen(
            [
                powershell_path,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper_copy),
                "-ManifestPath",
                str(manifest_path),
                "-TargetDirectory",
                str(target_root),
                "-ParentPid",
                str(os.getpid()),
                "-ExecutableName",
                executable_path.name,
            ],
            cwd=str(handoff_root),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        shutil.rmtree(handoff_root, ignore_errors=True)
        raise AppUpdateError(f"could not start updater helper: {exc}") from exc


__all__ = [
    "APP_MANIFEST_ASSET_NAME",
    "AppUpdateError",
    "AppUpdateManifest",
    "AppUpdateResult",
    "DEFAULT_APP_FEED_URL",
    "check_app_update",
    "spawn_windows_updater",
]
