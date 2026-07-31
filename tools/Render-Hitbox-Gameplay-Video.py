"""Render a short deterministic gameplay clip with real combat debug geometry."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.entities import Enemy
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


def _enemy(game: FadesGame, enemy_id: int, x: float, depth: float) -> Enemy:
    enemy = Enemy(enemy_id, "stick", x, depth, game.data["enemies"]["stick"])
    enemy.state = "chase"
    return enemy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--move", choices=("light", "heavy"), default="light")
    parser.add_argument("--depth-offsets", type=float, nargs="+", required=True)
    parser.add_argument("--x-offsets", type=float, nargs="+", required=True)
    args = parser.parse_args()
    if len(args.depth_offsets) != len(args.x_offsets):
        parser.error("offset lists must have matching lengths")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to render gameplay QA videos")
    pygame.init()
    pygame.display.set_mode((640, 360))
    canvas = pygame.Surface((640, 360))
    manager = InputManager(max_players=4, discover_controllers=False)
    game = FadesGame(manager, mute=True)
    game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
    game._start_stage()
    game.debug = True
    player = game.players[0]
    game.players[1].state = "eliminated"
    player.x, player.y, player.facing = 470.0, 250.0, 1
    game.camera_x = game._render_camera_x = 170.0
    game.enemies = [
        _enemy(game, 900 + index, player.x + x_offset, player.y + depth_offset)
        for index, (x_offset, depth_offset) in enumerate(zip(args.x_offsets, args.depth_offsets))
    ]
    move = (
        game.data["moves"]["light_combo"][0]
        if args.move == "light"
        else game.data["moves"]["heavy"]
    )
    player.combo_step = 0
    player.set_state(args.move, player._move_total(move))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg, "-y", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "640x360",
        "-framerate", "30", "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast",
        "-crf", "18", "-pix_fmt", "yuv420p", str(args.output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert process.stdin is not None
    font = pygame.font.Font(None, 28)
    small = pygame.font.Font(None, 19)
    hit_count = 0
    for frame in range(120):
        if frame == 42:
            hit_count = game.player_attack(player, move, args.move, already_hit=set(), play_whiff=False)
        game.draw(canvas)
        shade = pygame.Surface((640, 54), pygame.SRCALPHA)
        shade.fill((3, 5, 10, 220))
        canvas.blit(shade, (0, 0))
        canvas.blit(font.render(args.title, True, (255, 240, 135)), (14, 8))
        status = "ATTACK INCOMING" if frame < 42 else f"CONFIRMED CONTACTS: {hit_count}"
        canvas.blit(small.render(status, True, (100, 245, 196)), (16, 35))
        canvas.blit(small.render("orange=current  magenta=sweep  cyan=contact", True, (239, 190, 255)), (318, 35))
        process.stdin.write(pygame.image.tostring(canvas, "RGB"))
    process.stdin.close()
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.wait() != 0:
        raise RuntimeError(stderr)
    game.close()
    manager.close()
    pygame.quit()
    print(args.output.resolve())


if __name__ == "__main__":
    main()
