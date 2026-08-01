"""Crash-safe breadcrumb logging for The Fades of Fate.

Call :func:`initialize_logging` once near program startup, then add compact
breadcrumbs around meaningful state changes.  Uncaught exceptions on both the
main thread and worker threads are recorded automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import traceback
from typing import Any, Callable, Optional, TypeVar
from uuid import uuid4


APP_NAME = "The Fades of Fate"
APP_SLUG = "the-fades-of-fate"
LOG_DIR_ENV = "FADES_OF_FATE_LOG_DIR"

_T = TypeVar("_T")
_LOCK = threading.RLock()
_STATE: Optional["LogState"] = None
_ORIGINAL_SYS_EXCEPTHOOK = sys.excepthook
_ORIGINAL_THREADING_EXCEPTHOOK = getattr(threading, "excepthook", None)


@dataclass(frozen=True)
class LogPaths:
    """Files created for the current game session."""

    directory: Path
    latest: Path
    session: Path


@dataclass
class LogState:
    """Internal session state returned by :func:`initialize_logging`."""

    logger: logging.Logger
    paths: LogPaths
    session_id: str
    version: str


def _now() -> datetime:
    return datetime.now().astimezone()


def _session_id() -> str:
    return f"{_now():%Y%m%d-%H%M%S}-{os.getpid()}"


def _packaged_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _user_log_directory() -> Path:
    android_private = os.environ.get("ANDROID_PRIVATE") or os.environ.get("ANDROID_ARGUMENT")
    if android_private:
        return Path(android_private).expanduser() / APP_SLUG / "logs"
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / APP_NAME / "logs"

    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / APP_SLUG / "logs"


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".write-test-{os.getpid()}-{uuid4().hex}"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _select_log_directory() -> Path:
    candidates: list[Path] = []
    override = os.environ.get(LOG_DIR_ENV)
    if override:
        candidates.append(Path(override).expanduser())
    candidates.extend(
        (
            _packaged_base() / "logs",
            _user_log_directory(),
            Path(tempfile.gettempdir()) / APP_SLUG / "logs",
        )
    )

    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key in seen:
            continue
        seen.add(key)
        if _is_writable_directory(candidate):
            return candidate.resolve()

    raise OSError("No writable directory is available for game logs.")


def initialize_logging(version: str = "dev") -> LogState:
    """Start the session logger and install process-wide exception hooks.

    Packaged builds first try ``logs`` beside the executable.  If that location
    is read-only, logging falls back to the current user's local application
    data directory.  ``FADES_OF_FATE_LOG_DIR`` can override both locations for
    development and automated tests.
    """

    global _STATE
    with _LOCK:
        if _STATE is not None:
            return _STATE

        directory = _select_log_directory()
        session_id = _session_id()
        paths = LogPaths(
            directory=directory,
            latest=directory / "latest.log",
            session=directory / f"session-{session_id}.log",
        )

        logger = logging.getLogger("fades_of_fate")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers.clear()
        logging.raiseExceptions = False

        formatter = logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d %(levelname)-8s "
            "[pid=%(process)d thread=%(threadName)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        for path, mode in ((paths.latest, "w"), (paths.session, "a")):
            handler = logging.FileHandler(path, mode=mode, encoding="utf-8")
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        _STATE = LogState(
            logger=logger,
            paths=paths,
            session_id=session_id,
            version=str(version),
        )
        install_exception_hooks()
        breadcrumb(
            "session_started",
            version=str(version),
            executable=str(sys.executable),
            packaged=bool(getattr(sys, "frozen", False)),
            working_directory=str(Path.cwd()),
            log_directory=str(directory),
        )
        return _STATE


def get_logger() -> logging.Logger:
    """Return the configured standard-library logger, initializing if needed."""

    return initialize_logging().logger


def get_log_paths() -> LogPaths:
    """Return the active ``latest.log`` and timestamped session log paths."""

    return initialize_logging().paths


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value if len(value) <= 2_000 else value[:1_997] + "..."
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:50]]
    if isinstance(value, dict):
        return {
            str(key): _safe_value(item)
            for key, item in list(value.items())[:50]
        }
    try:
        text = repr(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    return text if len(text) <= 2_000 else text[:1_997] + "..."


def breadcrumb(event: str, **details: Any) -> None:
    """Write a searchable, one-line gameplay breadcrumb.

    Example: ``breadcrumb("stage_loaded", stage="second_street", players=2)``.
    Values that are not directly JSON serializable are safely represented.
    """

    payload = {"event": str(event)}
    payload.update({str(key): _safe_value(value) for key, value in details.items()})
    initialize_logging().logger.info(
        "BREADCRUMB %s",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )


def _flush_handlers(state: LogState) -> None:
    for handler in state.logger.handlers:
        try:
            handler.flush()
        except Exception:
            pass


def _tail(path: Path, max_bytes: int = 65_536) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes), os.SEEK_SET)
            data = handle.read()
        return data.decode("utf-8", errors="replace")
    except OSError as error:
        return f"<latest log could not be read: {error}>"


def _safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    return cleaned[:48] or "unknown"


def _write_crash_report(
    context: str,
    exc_type: type[BaseException],
    exception: BaseException,
    tb: Any,
) -> Path:
    state = initialize_logging()
    _flush_handlers(state)
    stamp = f"{_now():%Y%m%d-%H%M%S-%f}"
    thread_name = _safe_filename_part(threading.current_thread().name)
    path = state.paths.directory / (
        f"crash-{stamp}-{os.getpid()}-{thread_name}.log"
    )
    trace = "".join(traceback.format_exception(exc_type, exception, tb))
    report = (
        f"{APP_NAME} crash report\n"
        f"time={_now().isoformat()}\n"
        f"session={state.session_id}\n"
        f"version={state.version}\n"
        f"context={context}\n"
        f"executable={sys.executable}\n"
        f"latest_log={state.paths.latest}\n"
        f"session_log={state.paths.session}\n\n"
        f"Traceback\n---------\n{trace}\n"
        f"Recent breadcrumbs\n------------------\n{_tail(state.paths.latest)}"
    )
    path.write_text(report, encoding="utf-8")
    return path


def capture_exception(
    context: str,
    exception: Optional[BaseException] = None,
    *,
    fatal: bool = False,
    **details: Any,
) -> Optional[Path]:
    """Record a caught exception and optionally create a crash report.

    Call this inside an ``except`` block.  Set ``fatal=True`` when the game must
    exit so a standalone timestamped report is produced.
    """

    if exception is None:
        current_type, current_exception, current_tb = sys.exc_info()
        if current_exception is None or current_type is None:
            raise RuntimeError("capture_exception() must receive an exception")
    else:
        current_exception = exception
        current_type = type(exception)
        current_tb = exception.__traceback__

    state = initialize_logging()
    payload = {str(key): _safe_value(value) for key, value in details.items()}
    state.logger.error(
        "EXCEPTION context=%s details=%s",
        context,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        exc_info=(current_type, current_exception, current_tb),
    )
    _flush_handlers(state)
    if not fatal:
        return None

    report = _write_crash_report(
        context, current_type, current_exception, current_tb
    )
    state.logger.critical("CRASH_REPORT path=%s", report)
    _flush_handlers(state)
    return report


def _sys_excepthook(
    exc_type: type[BaseException], exception: BaseException, tb: Any
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        _ORIGINAL_SYS_EXCEPTHOOK(exc_type, exception, tb)
        return
    try:
        capture_exception("main_thread_uncaught", exception, fatal=True)
    except Exception:
        pass
    _ORIGINAL_SYS_EXCEPTHOOK(exc_type, exception, tb)


def _threading_excepthook(args: Any) -> None:
    try:
        context = f"worker_thread_uncaught:{getattr(args.thread, 'name', 'unknown')}"
        capture_exception(context, args.exc_value, fatal=True)
    except Exception:
        pass
    if _ORIGINAL_THREADING_EXCEPTHOOK is not None:
        _ORIGINAL_THREADING_EXCEPTHOOK(args)


def install_exception_hooks() -> None:
    """Install uncaught exception hooks for the main and worker threads."""

    sys.excepthook = _sys_excepthook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _threading_excepthook


def guarded_main(main: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    """Run a game entry point and persist a crash report before re-raising."""

    initialize_logging()
    try:
        return main(*args, **kwargs)
    except KeyboardInterrupt:
        raise
    except BaseException as error:
        capture_exception("guarded_main", error, fatal=True)
        raise


def shutdown_logging(exit_reason: str = "normal") -> None:
    """Finish and flush the active session; safe to call more than once."""

    global _STATE
    with _LOCK:
        if _STATE is None:
            return
        state = _STATE
        payload = json.dumps(
            {"event": "session_ended", "reason": str(exit_reason)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        state.logger.info("BREADCRUMB %s", payload)
        _flush_handlers(state)
        for handler in list(state.logger.handlers):
            try:
                handler.close()
            finally:
                state.logger.removeHandler(handler)
        _STATE = None

