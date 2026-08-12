"""Tests for resolution-independent, pixel-crisp game presentation."""

from __future__ import annotations

import unittest

import pygame

from src.main import letterbox_viewport, logical_mouse_events, window_to_logical_position


class LetterboxViewportTests(unittest.TestCase):
    def test_exact_whole_number_scaling(self) -> None:
        self.assertEqual(
            letterbox_viewport((640, 360), (1920, 1080)),
            (0, 0, 1920, 1080),
        )

    def test_widescreen_and_tall_windows_center_an_integer_viewport(self) -> None:
        self.assertEqual(
            letterbox_viewport((640, 360), (1366, 768)),
            (43, 24, 1280, 720),
        )
        self.assertEqual(
            letterbox_viewport((640, 360), (1000, 1000)),
            (180, 320, 640, 360),
        )

    def test_tiny_window_uses_centered_aspect_fit_fallback(self) -> None:
        self.assertEqual(
            letterbox_viewport((640, 360), (320, 200)),
            (0, 10, 320, 180),
        )

    def test_invalid_dimensions_fail_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            letterbox_viewport((640, 0), (1280, 720))
        with self.assertRaisesRegex(ValueError, "width and height"):
            letterbox_viewport((640,), (1280, 720))

    def test_pointer_mapping_tracks_letterboxed_logical_targets(self) -> None:
        self.assertEqual(
            window_to_logical_position((640, 360), (1366, 768), (683, 384)),
            (320, 180),
        )
        self.assertIsNone(window_to_logical_position((640, 360), (1366, 768), (20, 20)))

    def test_mouse_events_use_the_logical_canvas_constant_at_runtime(self) -> None:
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (640, 360)})
        translated = logical_mouse_events([event], (1280, 720))
        self.assertEqual(len(translated), 1)
        self.assertEqual(translated[0].pos, (320, 180))


if __name__ == "__main__":
    unittest.main()
