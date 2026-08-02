"""Capture the fixed F4 proof scene, provenance overlay, and a short video."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from src.game import FadesGame, LOGICAL_SIZE  # noqa: E402
from src.input_manager import InputManager  # noqa: E402


def capture(output_dir: Path, *, seconds: float, fps: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pygame.init()
    pygame.display.set_mode(LOGICAL_SIZE)
    manager = InputManager(max_players=4, discover_controllers=False)
    game = FadesGame(manager, mute=True)
    canvas = pygame.Surface(LOGICAL_SIZE)
    encoder: subprocess.Popen[bytes] | None = None
    try:
        game._activate_visual_evidence_scene()
        for _ in range(30):
            game.update(1.0 / 60.0)

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            encoder = subprocess.Popen(
                [
                    ffmpeg,
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "rawvideo",
                    "-pixel_format",
                    "rgb24",
                    "-video_size",
                    f"{LOGICAL_SIZE[0]}x{LOGICAL_SIZE[1]}",
                    "-framerate",
                    str(fps),
                    "-i",
                    "-",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    str(output_dir / "pc_capture.mp4"),
                ],
                stdin=subprocess.PIPE,
            )

        frame_total = max(2, round(max(0.5, seconds) * fps))
        for frame_index in range(frame_total):
            for _ in range(2):
                game.update(1.0 / 60.0)
            game.draw(canvas)
            if frame_index == 0:
                pygame.image.save(canvas, output_dir / "pc_runtime_after.png")
            if encoder is not None and encoder.stdin is not None:
                encoder.stdin.write(pygame.image.tobytes(canvas, "RGB", False))

        if encoder is not None and encoder.stdin is not None:
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise RuntimeError("ffmpeg failed to encode the PC evidence video")

        game.debug = True
        game.draw(canvas)
        pygame.image.save(canvas, output_dir / "pc_provenance.png")
        (output_dir / "provenance.json").write_text(
            json.dumps(game.provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "loaded_assets.json").write_text(
            json.dumps(game.provenance["active_scenery_assets"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        if encoder is not None and encoder.poll() is None:
            if encoder.stdin is not None:
                encoder.stdin.close()
            encoder.wait()
        game.close()
        manager.close()
        pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    if args.fps < 1 or args.fps > 60:
        raise SystemExit("--fps must be between 1 and 60")
    capture(args.output_dir.resolve(), seconds=args.seconds, fps=args.fps)


if __name__ == "__main__":
    main()
