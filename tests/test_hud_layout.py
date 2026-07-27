"""Safe-area contracts for the compact local-co-op HUD."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.game import FadesGame, LOGICAL_SIZE


class CompactHudLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_one_to_four_player_cards_stay_in_safe_corners(self) -> None:
        safe = pygame.Rect(0, 0, *LOGICAL_SIZE)
        for scale in (0.80, 1.0, 1.50):
            for player_count in range(1, 5):
                with self.subTest(scale=scale, player_count=player_count):
                    cards = FadesGame._compact_hud_rects(player_count, scale)
                    self.assertEqual(len(cards), player_count)
                    self.assertTrue(all(safe.contains(card) for card in cards))
                    self.assertTrue(
                        all(not first.colliderect(second) for index, first in enumerate(cards) for second in cards[index + 1 :])
                    )

    def test_card_order_uses_left_right_then_lower_row(self) -> None:
        cards = FadesGame._compact_hud_rects(4, 1.0)
        self.assertLess(cards[0].x, cards[1].x)
        self.assertEqual(cards[0].y, cards[1].y)
        self.assertLess(cards[0].y, cards[2].y)
        self.assertEqual(cards[2].y, cards[3].y)


if __name__ == "__main__":
    unittest.main()
