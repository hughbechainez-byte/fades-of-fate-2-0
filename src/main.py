from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# Pointer translation is used by the live loop below, so this needs module
# scope rather than the local imports inside _run().
from src.config import LOGICAL_SIZE, is_android_runtime
from src.version import VERSION


def letterbox_viewport(
    logical_size: Sequence[int], window_size: Sequence[int]
) -> tuple[int, int, int, int]:
    """Return the centered viewport for crisp, aspect-correct presentation.

    Windows at least as large as the logical canvas use the largest whole-number
    pixel scale that fits. A very small window uses a proportional nearest-
    neighbor fallback so resizing can never produce a negative or clipped
    viewport.
    """
    if len(logical_size) != 2 or len(window_size) != 2:
        raise ValueError("logical_size and window_size must contain width and height")
    logical_width, logical_height = (int(value) for value in logical_size)
    window_width, window_height = (int(value) for value in window_size)
    if min(logical_width, logical_height, window_width, window_height) <= 0:
        raise ValueError("logical and window dimensions must be positive")

    whole_scale = min(
        window_width // logical_width,
        window_height // logical_height,
    )
    if whole_scale >= 1:
        viewport_width = logical_width * whole_scale
        viewport_height = logical_height * whole_scale
    else:
        fit_scale = min(
            window_width / logical_width,
            window_height / logical_height,
        )
        viewport_width = max(1, int(logical_width * fit_scale))
        viewport_height = max(1, int(logical_height * fit_scale))

    return (
        (window_width - viewport_width) // 2,
        (window_height - viewport_height) // 2,
        viewport_width,
        viewport_height,
    )


def window_to_logical_position(
    logical_size: Sequence[int], window_size: Sequence[int], position: Sequence[int]
) -> tuple[int, int] | None:
    """Map a physical pointer into the letterboxed logical canvas.

    ``None`` deliberately ignores clicks in the black bars around a resized
    game window, keeping every menu target aligned with its visible artwork.
    """

    if len(position) != 2:
        raise ValueError("position must contain x and y")
    left, top, viewport_width, viewport_height = letterbox_viewport(logical_size, window_size)
    x, y = (int(value) for value in position)
    if not (left <= x < left + viewport_width and top <= y < top + viewport_height):
        return None
    logical_width, logical_height = (int(value) for value in logical_size)
    mapped_x = min(logical_width - 1, (x - left) * logical_width // viewport_width)
    mapped_y = min(logical_height - 1, (y - top) * logical_height // viewport_height)
    return mapped_x, mapped_y


def logical_mouse_events(events: Sequence[object], window_size: Sequence[int]) -> list[object]:
    """Return pygame events whose pointer positions match the logical canvas."""

    import pygame

    translated: list[object] = []
    pointer_events = {pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP}
    for event in events:
        if event.type not in pointer_events:
            translated.append(event)
            continue
        position = window_to_logical_position(LOGICAL_SIZE, window_size, event.pos)
        if position is None:
            continue
        payload = dict(event.dict)
        payload["pos"] = position
        translated.append(pygame.event.Event(event.type, payload))
    return translated


def _draw_app_update_prompt(surface: object, latest_version: str, error: str | None = None) -> None:
    """Draw a small title-screen update gate without entering gameplay."""

    import pygame

    if not isinstance(surface, pygame.Surface):
        return
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((5, 8, 22, 232))
    surface.blit(overlay, (0, 0))
    title_font = pygame.font.Font(None, 30)
    body_font = pygame.font.Font(None, 21)
    small_font = pygame.font.Font(None, 17)
    title = title_font.render("UPDATE AVAILABLE", True, (255, 218, 76))
    body = body_font.render(f"Download version {latest_version} now?", True, (239, 245, 255))
    hint = small_font.render("ENTER / A: UPDATE     ESC / B: CONTINUE", True, (151, 191, 220))
    surface.blit(title, title.get_rect(center=(320, 112)))
    surface.blit(body, body.get_rect(center=(320, 148)))
    yes_rect = pygame.Rect(140, 186, 150, 38)
    no_rect = pygame.Rect(350, 186, 150, 38)
    pygame.draw.rect(surface, (27, 118, 93), yes_rect, border_radius=5)
    pygame.draw.rect(surface, (75, 83, 112), no_rect, border_radius=5)
    yes = body_font.render("UPDATE", True, (255, 255, 255))
    no = body_font.render("CONTINUE", True, (255, 255, 255))
    surface.blit(yes, yes.get_rect(center=yes_rect.center))
    surface.blit(no, no.get_rect(center=no_rect.center))
    surface.blit(hint, hint.get_rect(center=(320, 254)))
    if error:
        error_text = small_font.render(f"Update failed; continuing is safe: {error[:70]}", True, (255, 145, 145))
        surface.blit(error_text, error_text.get_rect(center=(320, 282)))


def _app_update_prompt_action(event: object) -> str | None:
    """Return ``accept`` or ``decline`` for title-screen update input."""

    import pygame

    if event.type == pygame.KEYDOWN:
        if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_y}:
            return "accept"
        if event.key in {pygame.K_ESCAPE, pygame.K_n}:
            return "decline"
    if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 0) == 1:
        point = getattr(event, "pos", (0, 0))
        if pygame.Rect(140, 186, 150, 38).collidepoint(point):
            return "accept"
        if pygame.Rect(350, 186, 150, 38).collidepoint(point):
            return "decline"
    if event.type == getattr(pygame, "JOYBUTTONDOWN", -1):
        if getattr(event, "button", -1) == 0:
            return "accept"
        if getattr(event, "button", -1) == 1:
            return "decline"
    if event.type == getattr(pygame, "CONTROLLERBUTTONDOWN", -1):
        if getattr(event, "button", -1) == getattr(pygame, "CONTROLLER_BUTTON_A", -2):
            return "accept"
        if getattr(event, "button", -1) == getattr(pygame, "CONTROLLER_BUTTON_B", -2):
            return "decline"
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="The Fades of Fate foundation demo")
    parser.add_argument("--self-test", action="store_true", help="run the hardware-free foundation QA suite and exit")
    parser.add_argument("--mute", action="store_true", help="disable music and sound")
    parser.add_argument("--windowed", action="store_true", help="start in a resizable 1280x720 window")
    parser.add_argument("--ko-preview", action="store_true", help="render the first hero as the KO engine preview")
    parser.add_argument(
        "--skip-content-update",
        action="store_true",
        help="skip all startup content feed checks",
    )
    parser.add_argument(
        "--skip-app-update",
        action="store_true",
        help="skip the Windows application update check",
    )
    parser.add_argument(
        "--auto-update",
        action="store_true",
        help="apply a verified Windows application update without prompting",
    )
    parser.add_argument(
        "--content-root",
        default=None,
        help="override where updated content is written",
    )
    parser.add_argument(
        "--content-feed",
        default=None,
        help="release feed URL for content pack discovery",
    )
    parser.add_argument(
        "--content-update-timeout",
        type=float,
        default=6.0,
        help="network timeout in seconds for content-update operations",
    )
    parser.add_argument(
        "--app-update-feed",
        default=None,
        help="latest-release API URL used for Windows application updates",
    )
    parser.add_argument(
        "--app-update-timeout",
        type=float,
        default=6.0,
        help="network timeout in seconds for application-update checks",
    )
    return parser.parse_args()


def initialize_pygame(android_runtime: bool) -> None:
    """Initialize only the SDL modules that are safe for the target platform."""

    import pygame

    if not android_runtime:
        pygame.mixer.pre_init(44_100, -16, 2, 512)
        pygame.init()
        try:
            pygame.joystick.init()
        except pygame.error:
            pass
        return

    # On some Motorola builds, pygame.init() asks SDL to open the audio
    # backend before the app has a usable audio device and Python exits from
    # the python-for-android bootstrap screen. AudioManager initializes the
    # mixer later inside its own failure-tolerant boundary.
    pygame.display.init()
    pygame.font.init()
    try:
        pygame.joystick.init()
    except pygame.error:
        pass


def _run() -> int:
    args = parse_args()
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    if args.ko_preview:
        os.environ["FADES_KO_PREVIEW"] = "1"
    if args.self_test:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    import pygame

    from src.config import CONTENT_ROOT_ENV, GAME_NAME, executable_root
    from src.app_update import (
        AppUpdateError,
        AppUpdateResult,
        check_app_update,
        spawn_windows_updater,
    )
    from src.content_update import (
        ContentUpdateError,
        apply_content_update_if_available,
    )
    from src.input_manager import InputManager
    from src.logger import breadcrumb, capture_exception, initialize_logging, shutdown_logging

    if args.content_root:
        os.environ[CONTENT_ROOT_ENV] = str(Path(args.content_root).expanduser().resolve())

    update_result = None
    if not args.self_test and not args.skip_content_update:
        try:
            update_result = apply_content_update_if_available(
                content_root_override=args.content_root,
                game_version=VERSION,
                feed_url=args.content_feed,
                timeout_seconds=args.content_update_timeout,
            )
        except Exception as exc:
            update_result = {
                "status": "failed",
                "updated": False,
                "content_root": os.path.expanduser(
                    args.content_root or os.environ.get("FADES_OF_FATE_CONTENT_ROOT", "")
                    or ""
                ),
                "local_revision": 0,
                "remote_revision": 0,
                "manifest_path": "",
                "reason": f"{type(exc).__name__}: {exc}",
            }

    if update_result and getattr(update_result, "status", "") in {"updated", "up_to_date"}:
        os.environ[CONTENT_ROOT_ENV] = str(update_result.content_root)

    # Import resource-owning modules only after a successful content update has
    # selected one complete root.  This prevents module-level atlases and
    # atmosphere data from binding to a stale or mixed tree before the updater
    # finishes.
    from src.game import FadesGame

    app_update_result: AppUpdateResult | None = None
    if (
        not args.self_test
        and not args.skip_app_update
        and not is_android_runtime()
        and os.name == "nt"
        and getattr(sys, "frozen", False)
    ):
        try:
            app_update_result = check_app_update(
                FadesGame.VERSION,
                feed_url=args.app_update_feed
                or os.environ.get("FADES_OF_FATE_APP_UPDATE_FEED", ""),
                timeout_seconds=args.app_update_timeout,
            )
        except Exception as exc:
            app_update_result = AppUpdateResult(
                "failed", False, FadesGame.VERSION, FadesGame.VERSION, reason=f"{type(exc).__name__}: {exc}"
            )
        if args.auto_update and app_update_result.available and app_update_result.manifest is not None:
            try:
                spawn_windows_updater(
                    app_update_result.manifest,
                    executable_root=executable_root(),
                    executable_path=Path(sys.executable),
                )
                return 0
            except AppUpdateError as exc:
                app_update_result = AppUpdateResult(
                    "failed",
                    False,
                    FadesGame.VERSION,
                    app_update_result.latest_version,
                    manifest=app_update_result.manifest,
                    reason=str(exc),
                )

    initialize_logging(FadesGame.VERSION)
    if update_result:
        breadcrumb("content_update", **(
            update_result.as_dict() if hasattr(update_result, "as_dict") else update_result
        ))
    if app_update_result:
        breadcrumb("app_update_check", **app_update_result.as_dict())

    android_runtime = is_android_runtime()
    initialize_pygame(android_runtime)

    if args.self_test:
        from src.self_test import run_foundation_self_test

        try:
            pygame.display.set_mode(LOGICAL_SIZE)
            report = run_foundation_self_test(executable_root() / "build")
            print(json.dumps(report, indent=2))
            return 0
        except Exception:
            capture_exception("foundation_self_test", fatal=True)
            return 1
        finally:
            pygame.quit()
            shutdown_logging()

    pygame.display.set_caption(GAME_NAME)
    if not android_runtime:
        icon_path = executable_root() / "assets" / "fades_of_fate_key_art.png"
        if icon_path.is_file():
            try:
                icon = pygame.image.load(str(icon_path))
                pygame.display.set_icon(icon)
            except pygame.error:
                pass

    flags = pygame.RESIZABLE | pygame.DOUBLEBUF
    windowed_size = (1280, 720)
    if android_runtime:
        # SDL's Android video backend owns the surface. Desktop resize/vsync
        # flags can fail before the first frame on some Motorola builds.
        try:
            window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        except pygame.error:
            window = pygame.display.set_mode(LOGICAL_SIZE)
        windowed_size = window.get_size()
    else:
        try:
            window = pygame.display.set_mode(windowed_size, flags, vsync=1)
        except TypeError:
            window = pygame.display.set_mode(windowed_size, flags)
    logical = pygame.Surface(LOGICAL_SIZE)
    clock = pygame.time.Clock()
    manager = InputManager(max_players=4, deadzone=0.22, discover_controllers=True)
    game = FadesGame(manager, mute=args.mute)
    fixed_hz = float(game.meta.get("fixed_hz", 60))
    if fixed_hz <= 0.0:
        raise ValueError("meta.fixed_hz must be positive")
    fixed_step = 1.0 / fixed_hz
    accumulator = 0.0
    fullscreen = False
    presentation: pygame.Surface | None = None
    presentation_size = (0, 0)
    breadcrumb("main_loop_started", display=window.get_size(), controllers=manager.connected_controllers)
    app_update_prompt = (
        app_update_result
        if app_update_result is not None and app_update_result.available and app_update_result.manifest is not None
        else None
    )
    app_update_error: str | None = None

    try:
        while game.running:
            frame_seconds = min(clock.tick(120) / 1000.0, 0.10)
            events = pygame.event.get()
            game_events = events
            if app_update_prompt is not None:
                game_events = []
                for event in events:
                    if event.type == pygame.QUIT:
                        game.running = False
                        app_update_prompt = None
                        continue
                    action = _app_update_prompt_action(event)
                    if action == "decline":
                        app_update_prompt = None
                        breadcrumb("app_update_declined")
                    elif action == "accept" and app_update_prompt is not None:
                        try:
                            spawn_windows_updater(
                                app_update_prompt.manifest,
                                executable_root=executable_root(),
                                executable_path=Path(sys.executable),
                            )
                            breadcrumb(
                                "app_update_accepted",
                                version=app_update_prompt.latest_version,
                            )
                            game.running = False
                            app_update_prompt = None
                        except AppUpdateError as exc:
                            app_update_error = str(exc)
                            breadcrumb("app_update_handoff_failed", reason=app_update_error)
                if not game.running:
                    continue
            for event in game_events:
                if not android_runtime and event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.DOUBLEBUF)
                    else:
                        window = pygame.display.set_mode(windowed_size, flags)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F12:
                    screenshot_dir = executable_root() / "screenshots"
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    screenshot_path = screenshot_dir / "latest.png"
                    pygame.image.save(logical, screenshot_path)
                    breadcrumb("screenshot_saved", path=str(screenshot_path), state=game.state)

            manager.process_events(game_events)
            game.handle_events(logical_mouse_events(game_events, window.get_size()))
            accumulator += frame_seconds
            steps = 0
            while accumulator >= fixed_step and steps < 5:
                game.update(fixed_step)
                if steps == 0:
                    # Pressed actions belong to one simulation step even when
                    # a slow render frame requires several catch-up updates.
                    manager.consume_pressed()
                accumulator -= fixed_step
                steps += 1
            if steps == 5:
                accumulator = 0.0
                breadcrumb("frame_catchup_capped", frame_seconds=frame_seconds)

            game.draw(logical)
            if app_update_prompt is not None and app_update_prompt.manifest is not None:
                _draw_app_update_prompt(logical, app_update_prompt.latest_version, app_update_error)
            window.fill((0, 0, 0))
            viewport_x, viewport_y, viewport_width, viewport_height = (
                letterbox_viewport(LOGICAL_SIZE, window.get_size())
            )
            viewport_size = (viewport_width, viewport_height)
            if viewport_size == LOGICAL_SIZE:
                window.blit(logical, (viewport_x, viewport_y))
            else:
                if presentation is None or presentation_size != viewport_size:
                    presentation = pygame.Surface(viewport_size).convert()
                    presentation_size = viewport_size
                # pygame.transform.scale is nearest-neighbor, preserving the
                # intentional pixel grid without smoothing it into blur.
                pygame.transform.scale(logical, viewport_size, presentation)
                window.blit(presentation, (viewport_x, viewport_y))
            pygame.display.flip()
    except Exception:
        capture_exception("main_loop", fatal=True)
        raise
    finally:
        breadcrumb("main_loop_stopped", state=game.state, frames=game.frame)
        game.close()
        manager.close()
        pygame.quit()
        shutdown_logging()
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
