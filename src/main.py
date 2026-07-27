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
from src.config import LOGICAL_SIZE


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="The Fades of Fate foundation demo")
    parser.add_argument("--self-test", action="store_true", help="run the hardware-free foundation QA suite and exit")
    parser.add_argument("--mute", action="store_true", help="disable music and sound")
    parser.add_argument("--windowed", action="store_true", help="start in a resizable 1280x720 window")
    parser.add_argument("--ko-preview", action="store_true", help="render the first hero as the KO engine preview")
    return parser.parse_args()


def _run() -> int:
    args = parse_args()
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    if args.ko_preview:
        os.environ["FADES_KO_PREVIEW"] = "1"
    if args.self_test:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    import pygame

    from src.config import GAME_NAME, executable_root
    from src.game import FadesGame
    from src.input_manager import InputManager
    from src.logger import breadcrumb, capture_exception, initialize_logging, shutdown_logging

    initialize_logging(FadesGame.VERSION)
    pygame.mixer.pre_init(44_100, -16, 2, 512)
    pygame.init()
    pygame.joystick.init()

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
    icon_path = executable_root() / "assets" / "fades_of_fate_key_art.png"
    if icon_path.is_file():
        try:
            icon = pygame.image.load(str(icon_path))
            pygame.display.set_icon(icon)
        except pygame.error:
            pass

    flags = pygame.RESIZABLE | pygame.DOUBLEBUF
    windowed_size = (1280, 720)
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

    try:
        while game.running:
            frame_seconds = min(clock.tick(120) / 1000.0, 0.10)
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
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

            manager.process_events(events)
            game.handle_events(logical_mouse_events(events, window.get_size()))
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
