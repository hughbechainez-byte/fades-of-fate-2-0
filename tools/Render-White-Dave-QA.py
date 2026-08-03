"""Render deterministic loading, selection, and gameplay proof for White Dave."""

from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


def main() -> None:
    pygame.init()
    pygame.display.set_mode((640, 360))
    canvas = pygame.Surface((640, 360))
    manager = InputManager(discover_controllers=False)
    game = FadesGame(manager, mute=True)
    output = PROJECT_ROOT / "build" / "white_dave_qa"
    output.mkdir(parents=True, exist_ok=True)
    game.state = "loading"
    game.draw(canvas)
    pygame.image.save(canvas, output / "loading_screen.png")
    game.state = "character_select"
    game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=3, confirmed=True)]
    game.draw(canvas)
    pygame.image.save(canvas, output / "character_select.png")
    game._start_stage()
    white_dave = next(player for player in game.players if player.character == "white_dave")
    white_dave.set_state("heavy", 0.52)
    white_dave.state_clock = 0.12
    game.draw(canvas)
    pygame.image.save(canvas, output / "gameplay_bolt_cutters.png")
    game.close()
    manager.close()
    pygame.quit()
    for name in ("loading_screen.png", "character_select.png", "gameplay_bolt_cutters.png"):
        print(output / name)


if __name__ == "__main__":
    main()
