"""Render deterministic screenshots of the boss handoff and victory results."""

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
    game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
    game._draw_character_select(canvas)
    output = Path("build")
    output.mkdir(exist_ok=True)
    pygame.image.save(canvas, output / "character_select_hero_portraits_qa.png")
    game._start_stage()

    game.draw(canvas)
    pygame.image.save(canvas, output / "gameplay_route_qa.png")

    game.encounter_index = len(game.data["encounters"]) - 1
    game._start_boss_transition()
    game._update_boss_transition(0.82)
    game.draw(canvas)
    pygame.image.save(canvas, output / "boss_loading_qa.png")

    game.level_stats.advance(124.0)
    game.players[0].score = 4210
    game.players[0].ko_count = 12
    game.players[0].hit_count = 53
    game.players[1].score = 2310
    game.players[1].ko_count = 7
    game.players[1].hit_count = 31
    game.record_player_damage(28.0)
    game._finish_level()
    game.victory_frame = game.victory_timeline.advance(0.86)
    game.draw(canvas)
    pygame.image.save(canvas, output / "victory_hug_qa.png")
    game.victory_frame = game.victory_timeline.advance(2.0)
    game.draw(canvas)
    pygame.image.save(canvas, output / "level_complete_qa.png")

    game.close()
    manager.close()
    pygame.quit()
    print(output / "character_select_hero_portraits_qa.png")
    print(output / "boss_loading_qa.png")
    print(output / "gameplay_route_qa.png")
    print(output / "victory_hug_qa.png")
    print(output / "level_complete_qa.png")


if __name__ == "__main__":
    main()
