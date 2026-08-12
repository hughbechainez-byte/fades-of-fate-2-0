"""Android/package entrypoint for the source-layout game."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import traceback


def _write_startup_failure(error: BaseException) -> None:
    """Persist pre-logger crashes so Android users can retrieve the cause."""

    roots = [
        os.environ.get("ANDROID_PRIVATE", "").strip(),
        os.environ.get("HOME", "").strip(),
        os.environ.get("ANDROID_ARGUMENT", "").strip(),
    ]
    payload = traceback.format_exc()
    for raw_root in roots:
        if not raw_root:
            continue
        try:
            directory = Path(raw_root).expanduser() / "the-fades-of-fate" / "logs"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "startup-crash.log").write_text(payload, encoding="utf-8")
            break
        except OSError:
            continue
    print(payload, file=sys.stderr)


def _main() -> int:
    from src.main import _run

    return _run()


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except SystemExit:
        raise
    except BaseException as error:
        _write_startup_failure(error)
        raise
